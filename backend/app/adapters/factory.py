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
    timeout: float = 30.0,
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
            embedding_model=embedding_model or "text-embedding-3-small",
            timeout=timeout,
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
    global _cached_adapter
    if _cached_adapter is not None:
        return _cached_adapter

    from app.core.config import settings

    _cached_adapter = build_adapter(
        adapter_type=settings.AI_ADAPTER,
        api_url=settings.AI_API_URL,
        api_key=settings.AI_API_KEY,
        chat_model=getattr(settings, "AI_CHAT_MODEL", None),
        embedding_model=getattr(settings, "AI_EMBEDDING_MODEL", None),
        timeout=getattr(settings, "AI_TIMEOUT", 30.0),
    )
    return _cached_adapter


_cached_adapter: AIServiceAdapter | None = None
