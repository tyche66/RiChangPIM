"""审计日志中间件 + 装饰器。

依据 docs/07-开发规范.md §7.2（日志内容要求）与 §7.3（审计动作清单）实现：

- 请求日志字段：method / path / user_id / ip / 耗时(ms) / status_code
- 业务层无需手动调用 `OperationLog`，统一由 ``@audit_action`` 装饰器自动写入
- 写入失败不阻塞业务响应，降级为 ERROR 级日志，便于运维定位审计缺口

提供两种互补机制：

1. ``audit_action(action, module, ...)`` —— 装饰器，显式声明单接口的审计动作，
   适合 §7.3 列出的具体动作（login / product_create / ...）。被装饰 endpoint
   必须声明 ``request: Request`` 形参（本装饰器从其读取 ip / user_id / body）。
2. ``AuditMiddleware`` —— 通用中间件，记录所有请求的请求日志（method/path/
   user_id/ip/耗时/status_code）到 logger，不替装饰器写 operation_log 表；
   装饰器负责命中 §7.3 清单的动作落库。二者职责分离避免重复落库。
"""

from __future__ import annotations

import functools
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("app.audit")

# Rolling window of (timestamp, status) for 5xx counting in the last 24h.
# Bounded: at one request per second for 24h this holds ~86k tuples (~few MB);
# if throughput ever exceeds that, switch to a time-bucketed counter.
_5XX_WINDOW_SECONDS = 24 * 3600
_5xx_events: deque[tuple[float, int]] = deque()
_5xx_lock = None  # lazily created to avoid importing threading at module import time


def _rolling_5xx_lock():
    global _5xx_lock
    if _5xx_lock is None:
        import threading

        _5xx_lock = threading.Lock()
    return _5xx_lock


def _record_5xx(status: int) -> None:
    if status < 500:
        return
    now = time.time()
    with _rolling_5xx_lock():
        _5xx_events.append((now, status))
        cutoff = now - _5XX_WINDOW_SECONDS
        while _5xx_events and _5xx_events[0][0] < cutoff:
            _5xx_events.popleft()


def http_5xx_last_24h() -> int:
    """Count HTTP 5xx responses in the last 24h (for /ops/status)."""
    now = time.time()
    cutoff = now - _5XX_WINDOW_SECONDS
    with _rolling_5xx_lock():
        while _5xx_events and _5xx_events[0][0] < cutoff:
            _5xx_events.popleft()
        return sum(1 for ts, _ in _5xx_events if ts >= cutoff)


def _client_ip(request: Request) -> str | None:
    """§7.2：ip 字段优先取 X-Forwarded-For，回退 client_host。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None
    client = request.client
    if client:
        return client.host
    return None


def _user_id_from_request(request: Request) -> str | None:
    """提取 user_id。

    优先读 request.state（PermissionChecker 已写入 user_id/role_code）；
    否则尽力从 Authorization Bearer token 解码 sub（兼容使用 get_current_user
    而未显式写 request.state 的端点）。
    """
    for attr in ("user_id", "sub", "uid"):
        val = getattr(request.state, attr, None)
        if val:
            return str(val)
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            try:
                from app.core.security import decode_access_token

                payload = decode_access_token(token)
                if isinstance(payload, dict):
                    for key in ("sub", "user_id", "uid"):
                        val = payload.get(key)
                        if val:
                            return str(val)
            except Exception:  # noqa: BLE001
                return None
    return None


async def _write_operation_log(
    *,
    user_id: str | None,
    module: str,
    action: str,
    response_code: int,
    ip: str | None,
    target_id: str | None = None,
    request_body: str | None = None,
) -> None:
    """独立 session 写入 ``operation_log``；失败降级 ERROR 日志，不抛出。

    使用独立 session 而非复用业务 db：避免业务事务已 commit/rollback 影响审计，
    也避免审计写入失败回滚掉业务结果。
    """
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.audit import OperationLog

        async with AsyncSessionLocal() as session:
            log = OperationLog(
                user_id=user_id,
                module=module,
                action=action,
                target_id=target_id,
                request_body=request_body,
                response_code=response_code,
                ip=ip,
            )
            session.add(log)
            await session.commit()
            await session.close()
    except Exception as exc:  # noqa: BLE001 - 审计不可影响主流程
        logger.error(
            "audit write failed action=%s module=%s user_id=%s response_code=%s: %r",
            action,
            module,
            user_id,
            response_code,
            exc,
            exc_info=True,
        )


async def _request_body_value(request: Request) -> str | None:
    """§7.2 错误日志要求 `请求参数摘要`；审计装饰器记录请求体前 200 字符。"""
    try:
        body = await request.body()
        if not body:
            return None
        text = body.decode("utf-8", errors="replace")
        return text[:200]
    except Exception:  # noqa: BLE001
        return None


def audit_action(
    action: str,
    module: str,
    *,
    failed_action: str | None = None,
    target_id_kwarg: str | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """审计装饰器。

    被装饰 endpoint 声明 ``request: Request`` 形参后，本装饰器在业务执行后自动
    写入 ``operation_log``。完全兼容原有响应行为：

    - 业务成功 → 记 ``action``，response_code 取业务 envelope 的 ``code``（无则 200）。
    - 业务抛 HTTPException（如登录失败 401）→ 当提供 ``failed_action`` 时记失败动作，
      response_code 取 ``exc.status_code``；随后原样抛出，响应行为不变。

    Args:
        action: §7.3 动作值，如 ``"login"`` / ``"product_create"``。
        module: 模块名，如 ``"auth"`` / ``"products"``。
        failed_action: 失败时动作值（如 ``"login_failed"``）；None 表示失败不单独记。
        target_id_kwarg: 业务返回结果中用于回填 ``target_id`` 的键名。
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Request | None = kwargs.get("request")
            if request is None:
                for a in args:
                    if isinstance(a, Request):
                        request = a
                        break

            start = time.perf_counter()
            ip = _client_ip(request) if request else None
            user_id = _user_id_from_request(request) if request else None
            body_summary = await _request_body_value(request) if request else None
            # V1.2 §5.2 / §6.5: redact request bodies for sensitive modules so
            # the audit log never persists passwords, AI keys or request-body
            # payloads from login/AI endpoints.
            if module in {"ai", "auth", "users"} and body_summary:
                body_summary = "[redacted]"

            try:
                result = await func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                status_code = getattr(exc, "status_code", 500)
                try:
                    if status_code >= 400 and failed_action:
                        await _write_operation_log(
                            user_id=user_id,
                            module=module,
                            action=failed_action,
                            response_code=int(status_code),
                            ip=ip,
                            request_body=body_summary,
                        )
                    elif status_code >= 400:
                        await _write_operation_log(
                            user_id=user_id,
                            module=module,
                            action=action,
                            response_code=int(status_code),
                            ip=ip,
                            request_body=body_summary,
                        )
                except Exception:  # noqa: BLE001
                    logger.error("audit(failed-path) bookkeeping error", exc_info=True)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.warning(
                    "audit action=%s module=%s user_id=%s ip=%s elapsed=%sms status=%s (raised)",
                    action,
                    module,
                    user_id,
                    ip,
                    elapsed_ms,
                    status_code,
                )
                raise

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            response_code = 200
            if isinstance(result, dict):
                code = result.get("code")
                if isinstance(code, int):
                    response_code = code
            elif hasattr(result, "code") and isinstance(result.code, int):
                response_code = int(result.code)

            target_id: str | None = None
            if target_id_kwarg:
                tid = None
                if target_id_kwarg in kwargs:
                    tid = kwargs[target_id_kwarg]
                if isinstance(result, dict):
                    tid = tid or result.get(target_id_kwarg)
                    if tid is None and isinstance(result.get("data"), dict):
                        tid = result["data"].get(target_id_kwarg)
                elif hasattr(result, target_id_kwarg):
                    tid = tid or getattr(result, target_id_kwarg)
                if tid is not None:
                    target_id = str(tid)

            await _write_operation_log(
                user_id=user_id,
                module=module,
                action=action,
                response_code=response_code,
                ip=ip,
                target_id=target_id,
                request_body=body_summary,
            )
            logger.info(
                "audit action=%s module=%s user_id=%s ip=%s elapsed=%sms status=%s",
                action,
                module,
                user_id,
                ip,
                elapsed_ms,
                response_code,
            )
            return result

        return wrapper

    return decorator


class AuditMiddleware(BaseHTTPMiddleware):
    """请求日志中间件（§7.2：method/path/user_id/ip/耗时/status_code）。

    职责仅限于输出请求日志到 logger，不写 ``operation_log`` 表（落库由
    ``@audit_action`` 装饰器按 §7.3 清单完成），避免重复落库。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[..., Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        method = request.method
        path = request.url.path
        ip = _client_ip(request)

        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            _record_5xx(500)
            try:
                from app.observability import metrics as _metrics

                _metrics.observe_http_request(method, request.url.path, 500, elapsed_ms / 1000.0)
            except Exception:  # noqa: BLE001
                pass
            logger.error(
                "request %s %s ip=%s user_id=%s elapsed=%sms status=500 error=%r",
                method,
                path,
                ip,
                _user_id_from_request(request),
                elapsed_ms,
                exc,
                exc_info=True,
            )
            raise

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        user_id = _user_id_from_request(request)
        _record_5xx(response.status_code)
        try:
            from app.observability import metrics as _metrics

            _metrics.observe_http_request(
                method, request.url.path, response.status_code, elapsed_ms / 1000.0
            )
        except Exception:  # noqa: BLE001
            pass
        logger.info(
            "request %s %s ip=%s user_id=%s elapsed=%sms status=%s",
            method,
            path,
            ip,
            user_id,
            elapsed_ms,
            response.status_code,
        )
        return response


__all__ = ["AuditMiddleware", "audit_action"]
