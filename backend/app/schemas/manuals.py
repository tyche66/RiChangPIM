from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductManualCreate(BaseModel):
    """Create a ProductManual linked to an existing Attachment.

    ``parsed_content`` is required when the caller already has extracted text
    (e.g. from a parser run out-of-band). When omitted, the manual is created
    in ``pending`` state and a parser/indexer worker is expected to fill it.
    """

    product_id: UUID
    attachment_id: UUID
    doc_type: Literal["manual", "spec", "datasheet", "certificate", "other"] = "manual"
    parsed_content: str | None = None


class ProductManualIndexRequest(BaseModel):
    """Request to trigger indexing of an already-created manual."""

    product_manual_id: UUID


class ProductManualChunkResponse(BaseModel):
    chunk_id: UUID
    product_manual_id: UUID
    product_id: UUID
    chunk_index: int
    chunk_text: str
    score: float | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductManualResponse(BaseModel):
    id: UUID
    product_id: UUID
    attachment_id: UUID
    doc_type: str
    parsed_content: str | None = None
    parse_status: str = "pending"
    parse_error: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    page_count: int | None = None
    index_status: str = "pending"
    index_error: str | None = None
    content_hash: str | None = None
    last_indexed_at: datetime | None = None
    create_time: datetime
    update_time: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductManualListResponse(BaseModel):
    list: list[ProductManualResponse]
    total: int


class RagAnswerRequest(BaseModel):
    query: str
    product_id: UUID | None = None
    top_k: int = Field(8, ge=1, le=32)
    min_score: float = Field(0.65, ge=0.0, le=1.0)
    session_id: str | None = None


class RagAnswerResponse(BaseModel):
    answer: str
    sources: list[ProductManualChunkResponse] = []
    bounded: bool = True
    insufficient_sources: bool = False
