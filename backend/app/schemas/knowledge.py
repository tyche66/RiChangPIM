from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentSchema(BaseModel):
    id: UUID
    source_type: str
    source_id: UUID | None = None
    product_id: UUID | None = None
    category_id: UUID | None = None
    brand_id: UUID | None = None
    attachment_id: UUID | None = None
    title: str
    doc_type: str
    version: str | None = None
    language: str | None = None
    content_hash: str
    parse_status: str
    index_status: str
    is_active: bool
    visibility: str
    required_permission: str | None = None
    metadata: dict | None = Field(default=None, alias="metadata_json")
    parser_name: str | None = None
    parser_version: str | None = None
    last_indexed_at: datetime | None = None
    effective_at: datetime | None = None
    expired_at: datetime | None = None
    create_time: datetime
    update_time: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class KnowledgeChunkSchema(BaseModel):
    id: UUID
    document_id: UUID
    product_id: UUID | None = None
    category_id: UUID | None = None
    brand_id: UUID | None = None
    chunk_index: int
    section_path: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    chunk_type: str
    chunk_text: str
    normalized_text: str | None = None
    token_count: int | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None
    content_hash: str
    metadata: dict | None = Field(default=None, alias="metadata_json")
    create_time: datetime
    update_time: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class KnowledgeIndexJobSchema(BaseModel):
    id: UUID
    source_type: str
    source_id: UUID | None = None
    operation: str
    status: str
    content_hash: str | None = None
    pipeline_version: str | None = None
    priority: int
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    heartbeat_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str | None = None
    created_by: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    create_time: datetime
    update_time: datetime

    model_config = ConfigDict(from_attributes=True)
