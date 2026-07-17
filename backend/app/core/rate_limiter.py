"""Per-user AI rate limiter backed by Redis.

Default: 10 requests per minute per user. Configurable via AI_RATE_LIMIT
(env, int) and AI_RATE_LIMIT_WINDOW (env, int seconds, default 60).

Fail-closed policy: if Redis is unreachable, the request is rejected with
a 503 rather than silently allowing unlimited traffic. A warning is logged
so operators can distinguish a rate-limit outage from normal rejections.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

import redis.asyncio as redis

logger = logging.getLogger(__name__)

DEFAULT_MAX_REQUESTS = 10
DEFAULT_WINDOW_SECONDS = 60


class RateLimiter:
    """Sliding-window counter rate limiter using Redis INCR/EXPIRE."""

    def __init__(
        self,
        redis_url: str,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._redis_url = redis_url
        self._max = max_requests
        self._window = window_seconds
        self._client: redis.Redis | None = None
        self._connected: bool | None = None

    async def _ensure_client(self) -> redis.Redis | None:
        if self._client is not None:
            return self._client
        try:
            client = redis.from_url(
                self._redis_url,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
                decode_responses=True,
            )
            await client.ping()
            self._client = client
            self._connected = True
            return client
        except Exception as exc:  # noqa: BLE001
            self._connected = False
            logger.warning("rate limiter redis unavailable: %r — fail-closed", exc)
            return None

    def _user_key(self, user_id: UUID | str) -> str:
        window_start = int(time.time()) // self._window
        return f"ai_rate:{user_id}:{window_start}"

    async def is_rate_limited(self, user_id: UUID | str) -> bool:
        """Return True if the user has exceeded the rate limit.

        Fail-closed: when Redis cannot be reached, returns True (reject).
        """
        client = await self._ensure_client()
        if client is None:
            # Redis unavailable — fail-closed: reject the request.
            return True

        key = self._user_key(user_id)
        try:
            current = await client.incr(key)
            if current == 1:
                await client.expire(key, self._window)
            return current > self._max
        except Exception as exc:  # noqa: BLE001
            self._connected = False
            logger.warning("rate limiter check failed (fail-closed): %r", exc)
            return True

    @property
    def available(self) -> bool:
        return self._connected is not False

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass
        self._client = None
        self._connected = None


# ---------------------------------------------------------------------------
# Module-level singleton — created lazily on first import / app startup.
# ---------------------------------------------------------------------------
_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return the process-global rate limiter instance."""
    global _limiter
    if _limiter is None:
        from app.core.config import settings

        max_req = getattr(settings, "AI_RATE_LIMIT", DEFAULT_MAX_REQUESTS)
        window = getattr(settings, "AI_RATE_LIMIT_WINDOW", DEFAULT_WINDOW_SECONDS)
        _limiter = RateLimiter(
            redis_url=settings.REDIS_URL,
            max_requests=int(max_req),
            window_seconds=int(window),
        )
    return _limiter
