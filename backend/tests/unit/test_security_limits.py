import time

import pytest

from app.core import security_limits
from app.core.config import settings
from app.observability import metrics


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.expiry: dict[str, int] = {}

    async def get(self, key):
        return self.values.get(key)

    async def incr(self, key):
        self.values[key] = str(int(self.values.get(key, "0")) + 1)
        return int(self.values[key])

    async def expire(self, key, seconds):
        self.expiry[key] = int(seconds)

    async def ttl(self, key):
        return self.expiry.get(key, 900)

    async def exists(self, key):
        return 1 if key in self.values else 0

    async def set(self, key, value, ex=None):
        self.values[key] = str(value)
        if ex is not None:
            self.expiry[key] = int(ex)

    async def delete(self, key):
        self.values.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()

    async def _get_client():
        return fake

    monkeypatch.setattr(security_limits, "_limits_enabled", lambda: True)
    monkeypatch.setattr(security_limits, "_fail_closed", lambda: True)
    monkeypatch.setattr(security_limits, "_get_client", _get_client)
    monkeypatch.setattr(settings, "SHARE_MAX_FAILURES", 5)
    monkeypatch.setattr(settings, "SHARE_RATE_LIMIT", 100)
    monkeypatch.setattr(settings, "SHARE_LOCKOUT_SECONDS", 900)
    return fake


@pytest.mark.anyio
async def test_share_failures_lock_the_token(fake_redis):
    for _ in range(5):
        await security_limits.record_share_failure("token", "10.0.0.1")
    allowed, retry_after = await security_limits.check_share_allowed(
        "token", "10.0.0.1"
    )
    assert not allowed
    assert retry_after > 0


@pytest.mark.anyio
async def test_jti_revocation_round_trip(fake_redis):
    expires_at = int(time.time()) + 60
    assert await security_limits.revoke_jti("jti-1", expires_at)
    assert await security_limits.is_jti_revoked("jti-1")
    assert not await security_limits.is_jti_revoked("jti-2")


@pytest.mark.anyio
async def test_jti_revocation_check_fails_closed_when_redis_unavailable(
    monkeypatch,
):
    """Redis 不可用时无法确认撤销列表：生产必须拒绝，不能放行。"""

    async def _no_client():
        return None

    monkeypatch.setattr(security_limits, "_limits_enabled", lambda: True)
    monkeypatch.setattr(security_limits, "_fail_closed", lambda: True)
    monkeypatch.setattr(security_limits, "_get_client", _no_client)
    assert await security_limits.is_jti_revoked("jti-any") is True


def test_metric_series_are_bounded():
    counter = metrics._Counter("pim_test_bounded", "unit", ("key",), max_series=2)
    counter.inc({"key": "a"})
    counter.inc({"key": "b"})
    counter.inc({"key": "c"})
    assert len(counter.values) == 2
    assert ("c",) not in counter.values

    gauge = metrics._Gauge("pim_test_gauge_bounded", "unit", ("key",), max_series=2)
    gauge.set({"key": "a"}, 1)
    gauge.set({"key": "b"}, 1)
    gauge.set({"key": "c"}, 1)
    assert len(gauge.values) == 2
