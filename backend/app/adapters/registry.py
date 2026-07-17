"""Re-exports for backward compatibility with the original __init__."""

from app.adapters.factory import build_adapter, get_ai_adapter

__all__ = ["build_adapter", "get_ai_adapter"]
