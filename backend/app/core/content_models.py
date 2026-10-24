"""Content-domain chat model whitelist.

Only model names explicitly configured in ``CONTENT_AI_CHAT_MODELS`` may be
selected by a client.  The default is ``CONTENT_AI_CHAT_MODEL`` and is used
whenever the request omits a model.  This module intentionally never exposes
the API key or any other credential.
"""

from __future__ import annotations

from app.core.config import settings


class ContentModelNotAllowedError(ValueError):
    """The requested model is not in the server-side allowlist."""


def parse_model_allowlist(raw: str | None) -> list[str]:
    """Parse the comma-separated allowlist, preserving order and removing duplicates."""
    models: list[str] = []
    seen: set[str] = set()
    for item in (raw or "").split(","):
        model = item.strip()
        if model and model not in seen:
            seen.add(model)
            models.append(model)
    return models


def get_content_model_catalog() -> tuple[list[str], str]:
    """Return ``(allowed_models, default_model)`` for the content domain."""
    allowed = parse_model_allowlist(settings.CONTENT_AI_CHAT_MODELS)
    default_model = (settings.CONTENT_AI_CHAT_MODEL or "").strip()
    return allowed, default_model


def resolve_content_model(model_name: str | None) -> str:
    """Resolve a request model to the server-approved model name.

    ``None``/blank means the configured default.  Any other value must be in
    the allowlist; the error is deliberately raised before an upstream call so
    a client cannot probe arbitrary model names.
    """
    allowed, default_model = get_content_model_catalog()
    selected = (model_name or "").strip()
    if not selected:
        return default_model
    if selected not in allowed:
        raise ContentModelNotAllowedError("所选模型不在服务端白名单中")
    return selected
