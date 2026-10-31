"""Redis-backed login/share throttling, JWT revocation and client-IP trust.

Production fails closed when Redis is unavailable. The test environment skips
Redis entirely so the existing unit/integration suite stays independent of
external services.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import time

import redis.asyncio as redis
from fastapi import Request

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _limits_enabled() -> bool:
    return settings.APP_ENV != "test"


def _fail_closed() -> bool:
    return settings.APP_ENV == "production"


async def _get_client() -> redis.Redis | None:
    global _client
    if not _limits_enabled():
        return None
    if _client is not None:
        return _client
    try:
        client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            decode_responses=True,
        )
        await client.ping()
        _client = client
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("security limits redis unavailable: %r", exc)
        return None


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def is_internal_request(request: Request) -> bool:
    if settings.APP_ENV != "production":
        return True
    try:
        addr = ipaddress.ip_address(get_client_ip(request))
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback


def _key(kind: str, identity: str, ip: str) -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    return f"pim:sec:{kind}:{digest}:{ip}"


async def _failure_locked(key: str, max_failures: int) -> tuple[bool, int]:
    if not _limits_enabled():
        return False, 0
    client = await _get_client()
    if client is None:
        return (_fail_closed(), 60)
    try:
        value = await client.get(key)
        if value is not None and int(value) >= max_failures:
            ttl = await client.ttl(key)
            return True, max(1, int(ttl))
        return False, 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("security limit read failed: %r", exc)
        return (_fail_closed(), 60)


async def _record_failure(key: str, window_seconds: int) -> None:
    if not _limits_enabled():
        return
    client = await _get_client()
    if client is None:
        return
    try:
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, window_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("security limit write failed: %r", exc)


async def _clear(key: str) -> None:
    if not _limits_enabled():
        return
    client = await _get_client()
    if client is None:
        return
    try:
        await client.delete(key)
    except Exception:  # noqa: BLE001
        pass


async def _rate_allowed(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    if not _limits_enabled():
        return True, 0
    client = await _get_client()
    if client is None:
        return (not _fail_closed(), 60)
    try:
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, window_seconds)
        if current > limit:
            ttl = await client.ttl(key)
            return False, max(1, int(ttl))
        return True, 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("security rate limit failed: %r", exc)
        return (not _fail_closed(), 60)


async def check_login_allowed(username: str, ip: str) -> tuple[bool, int]:
    locked, retry_after = await _failure_locked(
        _key("login_fail", username.lower(), ip), settings.LOGIN_MAX_FAILURES
    )
    return not locked, retry_after


async def record_login_failure(username: str, ip: str) -> None:
    await _record_failure(
        _key("login_fail", username.lower(), ip), settings.LOGIN_LOCKOUT_SECONDS
    )


async def clear_login_failures(username: str, ip: str) -> None:
    await _clear(_key("login_fail", username.lower(), ip))


async def check_share_allowed(token: str, ip: str) -> tuple[bool, int]:
    allowed, retry_after = await _rate_allowed(
        _key("share_req", token, ip),
        settings.SHARE_RATE_LIMIT,
        settings.SHARE_RATE_WINDOW,
    )
    if not allowed:
        return False, retry_after
    locked, retry_after = await _failure_locked(
        _key("share_fail", token, ip), settings.SHARE_MAX_FAILURES
    )
    return not locked, retry_after


async def record_share_failure(token: str, ip: str) -> None:
    await _record_failure(
        _key("share_fail", token, ip), settings.SHARE_LOCKOUT_SECONDS
    )


async def clear_share_failures(token: str, ip: str) -> None:
    await _clear(_key("share_fail", token, ip))


async def revoke_jti(jti: str, exp: int) -> bool:
    if not _limits_enabled():
        return True
    client = await _get_client()
    if client is None:
        return not _fail_closed()
    ttl = max(1, int(exp) - int(time.time()))
    try:
        await client.set(f"pim:sec:revoked:{jti}", "1", ex=ttl)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("jwt revoke failed: %r", exc)
        return not _fail_closed()


async def is_jti_revoked(jti: str) -> bool:
    """检查 access/refresh token 的 jti 是否已被撤销。

    返回 False 只表示"确认未撤销"。Redis 不可用或查询异常时无法确认撤销
    列表，生产环境（``_fail_closed()``）必须返回 True 拒绝该 token，否则
    登出/轮换后已撤销的 token 会在故障窗口内继续有效；非生产环境保留
    便利性，返回 False。
    """
    if not _limits_enabled():
        return False
    client = await _get_client()
    if client is None:
        return _fail_closed()
    try:
        return bool(await client.exists(f"pim:sec:revoked:{jti}"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("jwt revoke check failed: %r", exc)
        return _fail_closed()


async def close_security_limits() -> None:
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:  # noqa: BLE001
            pass
    _client = None
