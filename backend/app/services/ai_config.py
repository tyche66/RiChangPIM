"""AI 配置解析（AI 配置中心）。

DB 覆盖层 + 环境回落；进程内缓存带 TTL，写操作后主动刷新。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.models.ai_config import AiProviderConfig

SCOPE_KNOWLEDGE = "knowledge"
SCOPE_CONTENT = "content"

#: scope -> 中文标签。顺序即前端展示顺序。
SCOPES: tuple[tuple[str, str], ...] = (
    (SCOPE_KNOWLEDGE, "选品检索 / 知识库（主 AI）"),
    (SCOPE_CONTENT, "内容工坊 / 独立选题"),
)

CACHE_TTL_SECONDS = 15.0

_cache: dict[str, tuple[float, "AiConfig | None"]] = {}


@dataclass(frozen=True)
class AiConfig:
    """解析后的生效配置。``source`` 记录该快照来自 DB 覆盖还是环境变量。"""

    scope: str
    api_url: str | None = None
    api_key: str | None = None
    chat_model: str | None = None
    chat_models: tuple[str, ...] = ()
    embedding_model: str | None = None
    embedding_api_url: str | None = None
    embedding_api_key: str | None = None
    timeout_seconds: float | None = None
    enabled: bool = True
    source: str = "env"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_models(raw: Any) -> tuple[str, ...]:
    models: list[str] = []
    seen: set[str] = set()
    for item in str(raw or "").split(","):
        model = item.strip()
        if model and model not in seen:
            seen.add(model)
            models.append(model)
    return tuple(models)


def _parse_timeout(raw: Any) -> float | None:
    text = _clean(raw)
    if text is None:
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _env_config(scope: str) -> AiConfig:
    """环境变量快照。DB 未覆盖时全部消费方看到的都是它。"""
    if scope == SCOPE_CONTENT:
        return AiConfig(
            scope=scope,
            api_url=_clean(settings.CONTENT_AI_API_URL),
            api_key=_clean(settings.CONTENT_AI_API_KEY),
            chat_model=_clean(settings.CONTENT_AI_CHAT_MODEL),
            chat_models=_parse_models(settings.CONTENT_AI_CHAT_MODELS),
            timeout_seconds=_parse_timeout(settings.CONTENT_AI_TIMEOUT),
            source="env",
        )
    return AiConfig(
        scope=scope,
        api_url=_clean(settings.AI_API_URL),
        api_key=_clean(settings.AI_API_KEY),
        chat_model=_clean(settings.AI_CHAT_MODEL),
        chat_models=(),
        embedding_model=_clean(settings.AI_EMBEDDING_MODEL),
        embedding_api_url=_clean(settings.AI_EMBEDDING_API_URL),
        embedding_api_key=_clean(settings.AI_EMBEDDING_API_KEY),
        timeout_seconds=_parse_timeout(settings.AI_TIMEOUT),
        source="env",
    )


def _merge(row: AiProviderConfig, env: AiConfig) -> AiConfig:
    """逐字段覆盖：DB 非空字段胜出，其余回落环境变量。

    行被禁用时整行忽略（等价于没配），保证 fail-open 到既有部署行为。
    """
    return AiConfig(
        scope=row.scope,
        api_url=_clean(row.api_url) or env.api_url,
        api_key=_clean(row.api_key) or env.api_key,
        chat_model=_clean(row.chat_model) or env.chat_model,
        chat_models=_parse_models(row.chat_models) or env.chat_models,
        embedding_model=_clean(row.embedding_model) or env.embedding_model,
        embedding_api_url=_clean(row.embedding_api_url) or env.embedding_api_url,
        embedding_api_key=_clean(row.embedding_api_key) or env.embedding_api_key,
        timeout_seconds=_parse_timeout(row.timeout_seconds) or env.timeout_seconds,
        enabled=True,
        source="db",
    )


async def load_config(scope: str, db: Any) -> AiConfig:
    """从数据库解析单个 scope 的生效配置（供启动预热与管理端读取）。"""
    env = _env_config(scope)
    result = await db.execute(
        select(AiProviderConfig).where(
            AiProviderConfig.scope == scope,
            AiProviderConfig.is_deleted.is_(False),
        )
    )
    row = result.scalars().first()
    if row is None or not row.enabled:
        return env
    return _merge(row, env)


async def load_all_configs(db: Any) -> dict[str, AiConfig]:
    return {scope: await load_config(scope, db) for scope, _ in SCOPES}


async def refresh_cache(db_factory: Any = None) -> dict[str, AiConfig]:
    """重载进程内缓存。DB 不可用时保留旧快照，不把配置清成 env。"""
    global _cache
    from app.core.database import AsyncSessionLocal

    factory = db_factory or AsyncSessionLocal
    try:
        async with factory() as db:
            configs = await load_all_configs(db)
    except Exception:
        # 启动早期/DB 抖动：保留旧缓存，让消费方继续用上一次的有效配置。
        return {scope: peek(scope) or _env_config(scope) for scope, _ in SCOPES}
    now = time.monotonic()
    for scope, config in configs.items():
        _cache[scope] = (now, config)
    return configs


def peek(scope: str) -> AiConfig | None:
    """读缓存快照；过期或未预热时返回 None（调用方回落 env）。"""
    entry = _cache.get(scope)
    if entry is None:
        return None
    loaded_at, config = entry
    if time.monotonic() - loaded_at > CACHE_TTL_SECONDS:
        return None
    return config


def get_config(scope: str) -> AiConfig:
    """同步读取生效配置：缓存优先，过期/缺失回落环境变量。"""
    return peek(scope) or _env_config(scope)


def invalidate_cache() -> None:
    _cache.clear()


def mask_key(key: str | None) -> str | None:
    """密钥掩码：只留后 4 位，长度不足或为空时返回 None。"""
    text = _clean(key)
    if not text or len(text) < 5:
        return None
    return f"****{text[-4:]}"


def config_to_dict(config: AiConfig) -> dict[str, Any]:
    """管理端读取视图：密钥只出掩码，绝不出明文。"""
    return {
        "scope": config.scope,
        "api_url": config.api_url,
        "api_key_masked": mask_key(config.api_key),
        "has_api_key": bool(config.api_key),
        "chat_model": config.chat_model,
        "chat_models": list(config.chat_models),
        "embedding_model": config.embedding_model,
        "embedding_api_url": config.embedding_api_url,
        "embedding_api_key_masked": mask_key(config.embedding_api_key),
        "timeout_seconds": config.timeout_seconds,
        "enabled": config.enabled,
        "source": config.source,
    }
