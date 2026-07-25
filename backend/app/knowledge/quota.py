from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QuotaCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID | None = None
    role_code: str | None = None
    capability: Literal["chat", "embedding", "reranking", "planning"] = "chat"
    provider: str | None = None
    model: str | None = None
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    trace_id: str


class QuotaCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: bool
    remaining_count: int | None = None
    remaining_amount: float | None = None
    remaining_tokens: int | None = None
    retry_after_seconds: int | None = None
    reason_code: str | None = None
    reason_message: str | None = None
    degraded_capabilities: list[str] = []


class QuotaUsageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: str
    user_id: UUID | None = None
    role_code: str | None = None
    provider: str | None = None
    model: str | None = None
    capability: Literal["chat", "embedding", "reranking", "planning"] = "chat"
    direction: Literal["input", "output"] | None = None
    tokens: int = 0
    estimated_cost_usd: float | None = None
    latency_ms: int = 0
    status: Literal["ok", "error", "timeout", "rate_limited"] = "ok"
    timestamp: datetime


@runtime_checkable
class QuotaChecker(Protocol):
    async def check(self, request: QuotaCheckRequest) -> QuotaCheckResponse: ...
    async def record(self, record: QuotaUsageRecord) -> None: ...


class NoOpQuotaChecker:
    async def check(self, request: QuotaCheckRequest) -> QuotaCheckResponse:
        return QuotaCheckResponse(allowed=True)

    async def record(self, record: QuotaUsageRecord) -> None:
        return None


def get_quota_checker() -> QuotaChecker:
    return NoOpQuotaChecker()
