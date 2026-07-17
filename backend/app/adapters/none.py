from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from .base import AIServiceAdapter
from .exceptions import AIAdapterUnavailableError

_UNAVAILABLE_ANSWER = "AI 能力中心未配置，请在 .env 中设置 AI_ADAPTER。"


class NoneAdapter(AIServiceAdapter):
    """No-op adapter when AI is not configured.

    Explicitly signals unavailability: every method returns the standard
    contract shape with empty / sentinel values, and ``available`` is False.
    """

    def __init__(self) -> None:
        self.available = False

    # ---------- chat ----------
    async def chat(
        self,
        session_id: str,
        message: str,
        history: list[dict[str, str]],
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "answer": _UNAVAILABLE_ANSWER,
            "sources": [],
            "tool_calls": [],
            "session_id": session_id,
            "model": None,
            "usage": None,
        }

    async def chat_stream(
        self,
        session_id: str,
        message: str,
        history: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        yield {
            "type": "error",
            "session_id": session_id,
            "error": _UNAVAILABLE_ANSWER,
        }

    # ---------- embeddings ----------
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise AIAdapterUnavailableError(_UNAVAILABLE_ANSWER)

    async def embed_one(self, text: str) -> list[float]:
        raise AIAdapterUnavailableError(_UNAVAILABLE_ANSWER)

    # ---------- tool calls ----------
    def parse_tool_calls(self, raw_response: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    # ---------- session management ----------
    async def manage_session(
        self, action: str, session_id: str | None = None
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "backend": "none",
            "available": False,
        }

    # ---------- lifecycle ----------
    async def aclose(self) -> None:
        pass
