"""内容工坊 Pydantic schemas（HLD §8.5 / §9.1）。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContentGenerateRequest(BaseModel):
    """POST /api/v1/content/batches 请求体。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255)
    customer_id: UUID | None = None
    project_id: UUID | None = None
    product_ids: list[UUID] = Field(default_factory=list, max_length=10)
    topic: str = Field(..., min_length=1, max_length=2000)
    platform: str = Field(..., pattern="^(xhs|douyin|moments|seo|other)$")
    tone: str | None = Field(None, max_length=32)
    requested_count: int = Field(default=3, ge=1, le=5)


class ContentItemResult(BaseModel):
    id: UUID
    title: str | None = None
    body: str
    hashtags: list[str] = Field(default_factory=list)
    verified: bool = True
    warnings: list[str] = Field(default_factory=list)


class ContentBatchResponse(BaseModel):
    batch_id: UUID
    status: str
    items: list[ContentItemResult] = Field(default_factory=list)


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=255)


class AdoptParams(BaseModel):
    confirm: bool = False


class PublishRequest(BaseModel):
    platform: str = Field(..., pattern="^(xhs|douyin|moments|seo|other)$")
    account_name: str | None = Field(None, max_length=128)
    publish_url: str = Field(..., min_length=1, max_length=1024)
    published_at: datetime | None = None
    video_attachment_id: UUID | None = None
    external_ref: str | None = Field(None, max_length=128)


class PublishResponse(BaseModel):
    publication_id: UUID
    content_item_id: UUID
    platform: str
    publish_url: str
    published_at: datetime


class MetricEntry(BaseModel):
    publication_id: UUID
    views: int | None = Field(None, ge=0)
    likes: int | None = Field(None, ge=0)
    comments: int | None = Field(None, ge=0)
    shares: int | None = Field(None, ge=0)
    favorites: int | None = Field(None, ge=0)
    leads: int | None = Field(None, ge=0)
    captured_at: datetime | None = None
    captured_date: str | None = None
    source: str = Field(default="manual", pattern="^(manual|import)$")

    @field_validator("captured_date")
    @classmethod
    def validate_date(cls, v):
        if v is None:
            return None
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("captured_date must be YYYY-MM-DD") from None
        return v


class MetricResponse(BaseModel):
    id: UUID
    publication_id: UUID
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    favorites: int | None = None
    leads: int | None = None
    captured_at: datetime
    captured_date: str
    source: str


class MetricImportRow(BaseModel):
    row: int
    status: str
    publish_url: str | None = None
    captured_date: str | None = None
    error_code: str | None = None
    error_msg: str | None = None


class MetricImportResponse(BaseModel):
    total: int
    created: int = 0
    updated: int = 0
    failed: int = 0
    errors: list[MetricImportRow] = Field(default_factory=list)
    error_file_url: str | None = None


class ContentBatchDetail(BaseModel):
    id: UUID
    title: str
    customer_id: UUID | None = None
    customer_name: str | None = None
    project_id: UUID | None = None
    project_name: str | None = None
    product_ids: list[str] = Field(default_factory=list)
    topic: str
    platform: str
    tone: str | None = None
    requested_count: int
    status: str
    error_msg: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str
    latency_ms: int | None = None
    create_time: datetime
    model_config = {"from_attributes": True}


class ContentItemDetail(BaseModel):
    id: UUID
    batch_id: UUID
    item_type: str
    platform: str
    title: str | None = None
    body: str
    hashtags: list[str] = Field(default_factory=list)
    status: str
    display_state: str
    adopted_by: UUID | None = None
    adopted_at: datetime | None = None
    rejected_reason: str | None = None
    produced_at: datetime | None = None
    published_at: datetime | None = None
    closed_at: datetime | None = None
    edited: bool = False
    verified_payload: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    external_ref: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    generation_version: str
    create_time: datetime
    model_config = {"from_attributes": True}


class ContentItemUpdate(BaseModel):
    """PUT /api/v1/content/items/{id} 请求体。"""

    title: str | None = Field(None, max_length=255)
    body: str | None = None
    hashtags: list[str] | None = None


class ContentPublicationDetail(BaseModel):
    id: UUID
    content_item_id: UUID
    platform: str
    account_name: str | None = None
    publish_url: str
    published_at: datetime
    video_attachment_id: UUID | None = None
    external_ref: str | None = None
    create_time: datetime
    model_config = {"from_attributes": True}
