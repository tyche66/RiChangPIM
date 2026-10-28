"""AI 配置中心单测：解析优先级、脱敏、禁用回落与路由权限。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import ai_config as ai_config_module
from app.services.ai_config import (
    SCOPE_CONTENT,
    SCOPE_KNOWLEDGE,
    AiConfig,
    _merge,
    config_to_dict,
    get_config,
    load_config,
    mask_key,
)


class _Result:
    def __init__(self, row):
        self._row = row

    def scalars(self):
        return self

    def first(self):
        return self._row


class _Db:
    def __init__(self, row):
        self._row = row

    async def execute(self, _stmt):
        return _Result(self._row)


def _row(**overrides):
    base = dict(
        scope=SCOPE_CONTENT,
        api_url="https://db.example.com/v1",
        api_key="db-secret-key",
        chat_model="db-model",
        chat_models="db-model,db-model-2",
        embedding_model=None,
        embedding_api_url=None,
        embedding_api_key=None,
        timeout_seconds="90",
        enabled=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_db_row_overrides_env_per_field():
    config = await load_config(SCOPE_CONTENT, _Db(_row()))
    assert config.source == "db"
    assert config.api_url == "https://db.example.com/v1"
    assert config.api_key == "db-secret-key"
    assert config.chat_model == "db-model"
    assert config.chat_models == ("db-model", "db-model-2")
    assert config.timeout_seconds == 90.0


@pytest.mark.asyncio
async def test_blank_db_fields_fall_back_to_env():
    config = await load_config(
        SCOPE_CONTENT,
        _Db(_row(api_url="", api_key=None, chat_model=None, chat_models="", timeout_seconds="")),
    )
    # 逐字段回落：空/None 的字段用 env，非空字段仍用 DB。
    assert config.api_url == "https://api.hcnsec.cn/v1"
    # env 未配 Key 时为 None，这正是"该字段无覆盖也无 env"的正确表现。
    assert config.api_key == ai_config_module._env_config(SCOPE_CONTENT).api_key
    assert config.chat_model == "step-5-preview"
    assert config.chat_models == ("step-5-preview", "sensenova-6.8-flash-lite")


@pytest.mark.asyncio
async def test_disabled_row_falls_back_to_env_entirely():
    config = await load_config(SCOPE_CONTENT, _Db(_row(enabled=False)))
    assert config.source == "env"
    assert config.api_url == "https://api.hcnsec.cn/v1"


@pytest.mark.asyncio
async def test_missing_row_uses_env():
    config = await load_config(SCOPE_CONTENT, _Db(None))
    assert config.source == "env"


def test_invalid_timeout_is_ignored():
    env = AiConfig(scope=SCOPE_CONTENT, timeout_seconds=180.0)
    merged = _merge(_row(timeout_seconds="abc"), env)
    assert merged.timeout_seconds == 180.0


def test_mask_key_keeps_only_last_four():
    assert mask_key("sk-abcdef1234") == "****1234"
    assert mask_key("short") == "****hort"
    assert mask_key(None) is None
    assert mask_key("   ") is None


def test_config_to_dict_never_leaks_plaintext_key():
    payload = config_to_dict(
        AiConfig(scope=SCOPE_KNOWLEDGE, api_key="super-secret-value", chat_model="m")
    )
    assert payload["has_api_key"] is True
    assert payload["api_key_masked"] == "****alue"
    assert "super-secret-value" not in repr(payload)


def test_sync_get_config_falls_back_to_env_without_cache(monkeypatch):
    monkeypatch.setattr(ai_config_module, "_cache", {})
    config = get_config(SCOPE_CONTENT)
    assert config.source == "env"


def test_cache_ttl_expires(monkeypatch):
    """TTL 只表示"该续期了"，过期快照仍然生效，绝不回落 env。

    2026-10-28 修复：旧行为是过期返回 None，调用方回落 env，把管理员在
    AI 配置中心显式改的模型静默丢回环境变量值（改完约 15 秒又变回旧模型）。
    """
    monkeypatch.setattr(
        ai_config_module,
        "_cache",
        {SCOPE_CONTENT: (0.0, AiConfig(scope=SCOPE_CONTENT, chat_model="cached"))},
    )
    snapshot = ai_config_module.peek(SCOPE_CONTENT)
    assert snapshot is not None
    assert snapshot.chat_model == "cached"
    assert get_config(SCOPE_CONTENT).chat_model == "cached"
