"""AI Service Adapter factory.

Resolves the implementation based on settings.AI_ADAPTER.
Adding a new engine means: one new module under app/adapters/ + one branch here.
Business code MUST go through `get_ai_adapter()` — never import concrete adapters directly.
"""

from __future__ import annotations

from app.adapters.base import AIServiceAdapter
from app.adapters.none import NoneAdapter


def build_adapter(
    adapter_type: str | None,
    *,
    api_url: str | None = None,
    api_key: str | None = None,
    chat_model: str | None = None,
    embedding_model: str | None = None,
    vision_model: str | None = None,
    embedding_api_url: str | None = None,
    embedding_api_key: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 2,
    allowed_chat_models: set[str] | frozenset[str] | None = None,
) -> AIServiceAdapter:
    """Build an adapter instance from a type selector.

    Fail-closed policy:
        * ``adapter_type`` is ``None``, ``"none"``, or unknown -> ``NoneAdapter``.
        * ``adapter_type == "openai"`` but ``api_key`` is missing -> ``NoneAdapter``.
        The lazy import avoids hard dependency on httpx/openai when the feature is off.
    """
    # Explicit unavailable — AI_ADAPTER=none or missing.
    if adapter_type is None or adapter_type == "none":
        return NoneAdapter()

    if adapter_type == "openai":
        if not api_key:
            return NoneAdapter()
        from app.adapters.openai import OpenAIAdapter, OpenAIConfig

        cfg = OpenAIConfig(
            api_key=api_key,
            api_url=api_url or "https://api.openai.com/v1",
            chat_model=chat_model or "gpt-4o-mini",
            embedding_model=embedding_model or "nvidia/nemotron-3-embed-1b:free",
            vision_model=vision_model,
            timeout=timeout,
            max_retries=max_retries,
            embedding_api_key=embedding_api_key,
            embedding_api_url=embedding_api_url,
            allowed_chat_models=frozenset(allowed_chat_models or ()),
        )
        return OpenAIAdapter(cfg)

    # Future engines — return NoneAdapter until implemented.
    if adapter_type in ("fastgpt", "dify", "ragflow"):
        return NoneAdapter()

    return NoneAdapter()


def get_ai_adapter() -> AIServiceAdapter:
    """FastAPI dependency / global accessor.

    Reads runtime settings directly. Singleton-per-process — adapter is stateless
    except for an httpx.AsyncClient, which is reused across requests.
    """
    global _cached_adapter, _cached_adapter_fingerprint

    from app.services.ai_config import get_config

    config = get_config("knowledge")
    fingerprint = _config_fingerprint(config)
    if _cached_adapter is not None and fingerprint == _cached_adapter_fingerprint:
        return _cached_adapter

    from app.core.config import settings

    adapter_type = settings.AI_ADAPTER
    if adapter_type == "openai" and not config.api_key:
        # DB 覆盖层显式清掉了 Key：fail-closed 到 NoneAdapter。
        adapter_type = "none"

    if adapter_type == "openai":
        from app.adapters.openai import register_vector_dim

        register_vector_dim(settings.AI_EMBEDDING_DIM)

    _cached_adapter = build_adapter(
        adapter_type=adapter_type,
        api_url=config.api_url or settings.AI_API_URL,
        api_key=config.api_key or settings.AI_API_KEY,
        chat_model=config.chat_model or getattr(settings, "AI_CHAT_MODEL", None),
        embedding_model=config.embedding_model
        or getattr(settings, "AI_EMBEDDING_MODEL", None),
        vision_model=config.vision_model
        or getattr(settings, "AI_VISION_MODEL", None),
        embedding_api_url=config.embedding_api_url
        or getattr(settings, "AI_EMBEDDING_API_URL", None),
        embedding_api_key=config.embedding_api_key
        or getattr(settings, "AI_EMBEDDING_API_KEY", None),
        timeout=config.timeout_seconds or getattr(settings, "AI_TIMEOUT", 30.0),
    )
    _cached_adapter_fingerprint = fingerprint
    return _cached_adapter


def _parse_model_allowlist(raw: str | None) -> set[str]:
    return {item.strip() for item in (raw or "").split(",") if item.strip()}


def _config_fingerprint(config) -> tuple:
    """配置指纹：任一字段变化都重建适配器（改 Key/模型后无需重启）。"""
    return (
        config.api_url,
        config.api_key,
        config.chat_model,
        config.embedding_model,
        config.embedding_api_url,
        config.embedding_api_key,
        config.vision_model,
        config.timeout_seconds,
        config.chat_models,
    )


def get_content_ai_adapter() -> AIServiceAdapter:
    """Get the content-domain adapter without touching the knowledge adapter."""
    global _cached_content_adapter, _cached_content_adapter_fingerprint

    from app.services.ai_config import get_config

    config = get_config("content")
    fingerprint = _config_fingerprint(config)
    if (
        _cached_content_adapter is not None
        and fingerprint == _cached_content_adapter_fingerprint
    ):
        return _cached_content_adapter

    allowed_models = set(config.chat_models)
    default_model = config.chat_model
    if not config.api_key or not allowed_models or default_model not in allowed_models:
        _cached_content_adapter = NoneAdapter()
        _cached_content_adapter_fingerprint = fingerprint
        return _cached_content_adapter

    _cached_content_adapter = build_adapter(
        adapter_type="openai",
        api_url=config.api_url,
        api_key=config.api_key,
        chat_model=default_model,
        timeout=config.timeout_seconds or 180.0,
        max_retries=0,
        allowed_chat_models=allowed_models,
    )
    _cached_content_adapter_fingerprint = fingerprint
    return _cached_content_adapter


_cached_adapter: AIServiceAdapter | None = None
_cached_adapter_fingerprint: tuple | None = None
_cached_content_adapter: AIServiceAdapter | None = None
_cached_content_adapter_fingerprint: tuple | None = None
