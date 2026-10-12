from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    source: str = Field("other")
    level: str | None = Field(None, pattern="^[ABC]$")
    phone: str | None = Field(None, max_length=64)
    wechat: str | None = Field(None, max_length=128)
    address: str | None = None
    budget_min: float | None = Field(None, ge=0)
    budget_max: float | None = Field(None, ge=0)
    style_preference: str | None = None
    remark: str | None = None
    owner_sales_id: UUID | None = None

    @field_validator("source")
    @classmethod
    def validate_source(cls, v):
        allowed = {"new_media", "store", "referral", "exhibition", "other"}
        if v not in allowed:
            raise ValueError(f"source must be one of {allowed}")
        return v


class CustomerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    source: str | None = None
    level: str | None = Field(None, pattern="^[ABC]$")
    phone: str | None = Field(None, max_length=64)
    wechat: str | None = Field(None, max_length=128)
    address: str | None = None
    budget_min: float | None = Field(None, ge=0)
    budget_max: float | None = Field(None, ge=0)
    style_preference: str | None = None
    remark: str | None = None


class CustomerResponse(BaseModel):
    id: UUID
    customer_no: str | None = None
    name: str
    source: str
    level: str | None = None
    stage: str
    owner_sales_id: UUID
    has_phone: bool
    budget_min: float | None = None
    budget_max: float | None = None
    style_preference: str | None = None
    remark: str | None = None
    project_count: int = 0
    last_activity_at: datetime | None = None
    create_time: datetime

    model_config = {"from_attributes": True}


class CustomerDetailResponse(BaseModel):
    id: UUID
    customer_no: str | None = None
    name: str
    source: str
    level: str | None = None
    stage: str
    owner_sales_id: UUID
    owner_sales_name: str | None = None
    phone_masked: str | None = None
    wechat_masked: str | None = None
    address_masked: str | None = None
    has_phone: bool
    budget_min: float | None = None
    budget_max: float | None = None
    style_preference: str | None = None
    remark: str | None = None
    last_activity_at: datetime | None = None
    create_time: datetime
    update_time: datetime


class StageTransitionRequest(BaseModel):
    to_stage: str
    reason: str | None = None


class PIIResponse(BaseModel):
    phone: str | None = None
    wechat: str | None = None
    address: str | None = None


class SummaryResponse(BaseModel):
    project_count: int = 0
    proposal_count: int = 0
    confirmed_amount: float | None = None
    confirmed_amount_visible: bool = True


class TimelineItem(BaseModel):
    type: str
    id: UUID
    content: str
    created_at: datetime
    operator_name: str | None = None


class TimelineResponse(BaseModel):
    list: list[TimelineItem]
    total: int
    page: int
    size: int
