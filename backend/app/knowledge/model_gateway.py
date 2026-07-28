from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.adapters.base import AIServiceAdapter
from app.adapters.exceptions import AIAdapterRateLimitError, AIAdapterTimeoutError
from app.adapters.none import NoneAdapter
from app.core.config import settings
from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError


@dataclass(frozen=True)
class ModelResult:
    answer: str
    provider: str | None
    model: str | None
    usage: dict[str, Any] | None
    latency_ms: int
    status: str


@runtime_checkable
class ModelGateway(Protocol):
    async def generate_answer(self, *, session_id: str, message: str, context: dict[str, Any], trace_id: str) -> ModelResult: ...


class AdapterModelGateway:
    def __init__(self, adapter: AIServiceAdapter) -> None:
        self.adapter = adapter

    def available(self) -> bool:
        return self.adapter is not None and not isinstance(self.adapter, NoneAdapter)

    async def generate_answer(self, *, session_id: str, message: str, context: dict[str, Any], trace_id: str) -> ModelResult:
        if not self.available():
            raise KnowledgeGatewayError(
                KnowledgeErrorCode.CAPABILITY_DISABLED,
                "AI 生成模型未配置，已返回可验证的结构化查询结果",
                status_code=503,
                retryable=False,
            )
        start = time.perf_counter()
        try:
            resp = await self.adapter.chat(
                session_id=session_id,
                message=message,
                history=[{"role": "system", "content": _context_summary(context)}],
                stream=False,
            )
        except AIAdapterTimeoutError as exc:
            raise KnowledgeGatewayError(KnowledgeErrorCode.MODEL_TIMEOUT, "AI 服务响应超时", status_code=504, retryable=True) from exc
        except AIAdapterRateLimitError as exc:
            raise KnowledgeGatewayError(KnowledgeErrorCode.MODEL_RATE_LIMIT, "AI 服务请求过于频繁", status_code=502, retryable=True) from exc
        except Exception as exc:
            raise KnowledgeGatewayError(KnowledgeErrorCode.MODEL_INVALID, "AI 服务暂不可用", status_code=503, retryable=True) from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ModelResult(
            answer=str(resp.get("answer") or ""),
            provider=settings.AI_ADAPTER,
            model=resp.get("model") or settings.AI_CHAT_MODEL,
            usage=resp.get("usage"),
            latency_ms=latency_ms,
            status="ok",
        )


def _context_summary(context: dict[str, Any]) -> str:
    return (
        "你是 RiChangPIM 只读产品知识助手。理解用户的自然语言问题，综合服务端提供的 "
        "facts/products/sources 给出直接、清晰的回答；不得将用户问题当作关键词搜索指令。"
        "只能依据这些上下文作答。价格、库存、成本、供应商等动态字段只能使用 facts/products "
        "中的当前结构化事实，不能从文档推断；资料未覆盖时明确说明。不得提出写入动作。"
        "引用知识文档时，在相应结论后标记其 source_id，例如 [chunk:... ]。"
        f"\nCONTEXT_JSON={context}"
    )
