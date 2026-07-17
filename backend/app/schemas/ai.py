from datetime import datetime
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

BoundedKeyword = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class StockStatus(Enum):
    in_stock = "in_stock"
    out_of_stock = "out_of_stock"
    preorder = "preorder"


class AIStatus(Enum):
    success = "success"
    parse_failed = "parse_failed"
    degraded = "degraded"
    unknown = "unknown"


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    history: list[dict[str, str]] = []
    stream: bool = False


class ChatResponse(BaseModel):
    answer: str
    sources: list = []
    tool_calls: list = []
    session_id: str | None = None


class EmbeddingRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=96)


class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dim: int


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = 8
    min_score: float = 0.65
    product_id: UUID | None = None


class RagSearchResponse(BaseModel):
    results: list
    query: str
    total: int


class RagIndexRequest(BaseModel):
    product_manual_id: UUID


class RagIndexResponse(BaseModel):
    indexed: int
    manual_id: UUID


class RecommendFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID | None = None
    max_face_price: float | None = Field(default=None, ge=0)
    tag_ids: list[UUID] = Field(default_factory=list, max_length=20)
    keywords: list[BoundedKeyword] = Field(default_factory=list, max_length=10)
    stock_status: StockStatus | None = None


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=20, ge=1, le=100)


class RecommendResponse(BaseModel):
    status: AIStatus
    filters_applied: dict[str, Any]
    products: list[dict[str, Any]]
    rationale: str
    total: int


class PolishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=1, max_length=500)
    item_reasons: list[str] = Field(..., min_length=1, max_length=50)
    industry_phrases: list[str] = Field(..., min_length=1, max_length=20)


class PolishResponse(BaseModel):
    status: AIStatus
    summary: str
    item_reasons: list[str]
    industry_phrases: list[str]
    proposal_id: UUID
    polished_at: datetime
