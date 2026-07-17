from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

# ---------------------------------------------------------------------------
# Non-streaming chat response contract
# ---------------------------------------------------------------------------
# Every concrete adapter MUST return these keys from ``chat()``.  Values may
# be empty (``""``, ``[]``, ``{}``, ``None``) when the upstream does not
# supply them, but the key itself must always be present so callers can rely
# on a stable shape.
CHAT_RESPONSE_FIELDS: tuple[str, ...] = (
    "answer",       # str  — assistant reply text
    "sources",      # list — retrieved RAG documents (may be empty)
    "tool_calls",   # list — normalized tool/function calls (may be empty)
    "session_id",   # str  — session identifier echoed back or synthesised
    "model",        # str  — upstream model identifier (may be None)
    "usage",        # dict — token usage stats (may be None)
)

# ---------------------------------------------------------------------------
# Streaming event contract
# ---------------------------------------------------------------------------
# ``chat_stream()`` yields dicts whose ``type`` is one of:
STREAM_EVENT_SESSION = "session"   # initial session metadata
STREAM_EVENT_DELTA = "delta"       # incremental text fragment
STREAM_EVENT_SOURCE = "source"     # retrieved source document
STREAM_EVENT_DONE = "done"         # final accumulated response
STREAM_EVENT_ERROR = "error"       # terminal error (no further events follow)
STREAM_EVENT_TYPES: tuple[str, ...] = (
    STREAM_EVENT_SESSION,
    STREAM_EVENT_DELTA,
    STREAM_EVENT_SOURCE,
    STREAM_EVENT_DONE,
    STREAM_EVENT_ERROR,
)


class AIServiceAdapter(ABC):
    """AI 服务适配器抽象基类
    解耦业务系统与下游 AI 引擎 (FastGPT / Dify / RagFlow)，统一 API 差异
    """

    @abstractmethod
    async def chat(
        self,
        session_id: str,
        message: str,
        history: list[dict[str, str]],
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """统一对话接口（非流式）
        :param session_id: 会话唯一标识，用于底层的 session 状态管理
        :param message: 当前用户输入的内容
        :param history: 历史对话上下文
        :return: 包含统一结构（answer, sources, tool_calls, session_id, model, usage）的 Dict
        """

    @abstractmethod
    async def chat_stream(
        self,
        session_id: str,
        message: str,
        history: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """统一流式对话接口
        :return: 异步生成器，产出统一格式的流式事件帧
            事件 type ∈ {session, delta, source, done, error}
        """

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化，供 RAG 入库使用。

        :param texts: 待嵌入的文本列表
        :return: 与 ``texts`` 等长的向量列表
        """

    @abstractmethod
    async def embed_one(self, text: str) -> list[float]:
        """单条文本向量化。

        :param text: 待嵌入的文本
        :return: 向量
        """

    @abstractmethod
    def parse_tool_calls(self, raw_response: dict[str, Any]) -> list[dict[str, Any]]:
        """统一解析和转化下游平台的 Tool Call / Function Call 格式
        :return: 抹平差异后的标准化 Tool Call 列表
        """

    @abstractmethod
    async def manage_session(
        self, action: str, session_id: str | None = None
    ) -> dict[str, Any]:
        """统一会话生命周期管理（创建、拉取、删除历史）"""

    @abstractmethod
    async def aclose(self) -> None:
        """释放适配器持有的连接池 / 客户端资源。

        子类应在持有长生命周期 HTTP 客户端时重写此方法。
        """
