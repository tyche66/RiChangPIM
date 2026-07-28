from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_SCOPE_FILTERS = {
    "product_no",
    "product_name",
    "category_id",
    "brand_id",
    "supplier_id",
    "status",
    "stock_status",
    "completeness_status",
    "material",
    "keyword",
    "has_image",
    "has_manual",
    "face_price_status",
}
FORBIDDEN_CLIENT_KEYS = {"role", "role_code", "permission", "permissions", "sensitivity", "security_level"}


class KnowledgeScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["global", "product", "product_list", "proposal"] = "global"
    product_ids: list[UUID] = Field(default_factory=list, max_length=20)
    filters: dict[str, Any] = Field(default_factory=dict)
    proposal_id: UUID | None = None

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, value: dict[str, Any]) -> dict[str, Any]:
        unknown = set(value) - ALLOWED_SCOPE_FILTERS
        if unknown:
            raise ValueError(f"scope.filters contains unsupported fields: {', '.join(sorted(unknown))}")
        return value


class KnowledgeCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stream: bool = False
    supports_actions: bool = False


class KnowledgeClientContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    page: str | None = None
    locale: str | None = "zh-CN"
    timezone: str | None = "Asia/Shanghai"

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        if isinstance(data, dict) and (set(data) & FORBIDDEN_CLIENT_KEYS):
            raise ValueError("client_context must not include role, permission, or sensitivity fields")
        return data


class KnowledgeQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=64)
    scope: KnowledgeScope = Field(default_factory=KnowledgeScope)
    capabilities: KnowledgeCapabilities = Field(default_factory=KnowledgeCapabilities)
    client_context: KnowledgeClientContext = Field(default_factory=KnowledgeClientContext)

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_top_level(cls, data: Any) -> Any:
        if isinstance(data, dict) and (set(data) & FORBIDDEN_CLIENT_KEYS):
            raise ValueError("request must not include role, permission, or sensitivity fields")
        return data


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: Literal["document", "product", "database_fact"]
    title: str
    product_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    page: int | None = None
    section: str | None = None
    quote: str | None = None
    observed_at: datetime | None = None
    access_policy: str = "filtered"
    score: float | None = None
    channel: str | None = None
    open_url: str | None = None


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: Literal["database_fact", "document", "inference"] = "database_fact"
    name: str
    value: Any
    observed_at: datetime | None = None
    product_id: str | None = None


class ProductCard(BaseModel):
    model_config = ConfigDict(extra="allow")


class QualityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    product_no: str
    product_name: str
    issue_type: str
    label: str


class KnowledgeUsage(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    degraded_reason: str | None = None


class KnowledgeQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    session_id: str
    answer: str
    facts: list[Fact] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    products: list[dict[str, Any]] = Field(default_factory=list)
    pending_actions: list[Any] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "insufficient"] = "medium"
    insufficient_sources: bool = False
    usage: KnowledgeUsage = Field(default_factory=KnowledgeUsage)
