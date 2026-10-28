"""AI 配置覆盖层的缓存语义回归。

2026-10-28 实测缺陷：管理员在 AI 配置中心把模型改成 agnes-3.0-flash，
约 15 秒后 ``peek()`` 因 TTL 过期返回 None，``get_config`` 改回落 env 的
agnes-2.5-flash，供应商后台看到的调用就一直停在旧模型。用户的显式配置
被静默丢弃，所以这里锁死「过期也返回旧快照，不回落 env」。
"""

from __future__ import annotations

import time

import pytest

from app.services import ai_config
from app.services.ai_config import CACHE_TTL_SECONDS, AiConfig, get_config, peek


def _seed_cache(scope: str, chat_model: str, *, age: float) -> None:
    ai_config._cache[scope] = (time.monotonic() - age, AiConfig(
        scope=scope, chat_model=chat_model, source="db",
    ))


@pytest.fixture(autouse=True)
def _clear_cache():
    ai_config._cache.clear()
    yield
    ai_config._cache.clear()


class TestConfigCacheSemantics:
    def test_fresh_snapshot_is_returned(self):
        _seed_cache("knowledge", "agnes-3.0-flash", age=0.0)
        assert peek("knowledge").chat_model == "agnes-3.0-flash"

    def test_expired_snapshot_is_still_returned_not_env(self):
        """过期快照必须继续生效：绝不给客户端回落到 env 的旧模型。"""
        _seed_cache("knowledge", "agnes-3.0-flash",
                    age=CACHE_TTL_SECONDS + 600)
        config = peek("knowledge")
        assert config is not None
        assert config.chat_model == "agnes-3.0-flash"
        assert config.source == "db"

    def test_get_config_keeps_db_override_after_ttl(self):
        _seed_cache("knowledge", "agnes-3.0-flash",
                    age=CACHE_TTL_SECONDS * 100)
        assert get_config("knowledge").chat_model == "agnes-3.0-flash"

    def test_empty_cache_still_falls_back_to_env(self):
        """没有快照时才回落 env——保持未预热时的 fail-open 行为。"""
        config = get_config("knowledge")
        assert config.source == "env"
        assert config.chat_model is not None

    def test_refresh_keeps_last_snapshot_when_db_unavailable(self):
        """DB 抖动时保留旧快照，不清空、不回落 env。"""
        import asyncio

        from app.services import ai_config as module

        _seed_cache("knowledge", "agnes-3.0-flash", age=1.0)

        class _FailingSession:
            async def __aenter__(self):
                raise RuntimeError("db down")

            async def __aexit__(self, *args):
                return False

        asyncio.run(module.refresh_cache(db_factory=_FailingSession))
        assert peek("knowledge").chat_model == "agnes-3.0-flash"
