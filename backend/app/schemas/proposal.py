from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProposalItemBase(BaseModel):
    product_id: UUID
    quantity: int = Field(1, ge=1)
    remark: str | None = None


class ProposalItemCreate(ProposalItemBase):
    pass


class ProposalItemResponse(ProposalItemBase):
    id: UUID
    product_no: str
    product_name: str
    face_price: float
    line_total: float
    cover_image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProposalBase(BaseModel):
    proposal_name: str
    customer_name: str | None = None
    creator_id: UUID


class ProposalCreate(ProposalBase):
    items: list[ProposalItemCreate] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list[ProposalItemCreate]) -> list[ProposalItemCreate]:
        if not v:
            raise ValueError("方案明细不可为空")
        return v


class ProposalUpdate(BaseModel):
    proposal_name: str | None = None
    customer_name: str | None = None
    items: list[ProposalItemCreate] | None = None


class ProposalResponse(ProposalBase):
    id: UUID
    proposal_no: str
    status: str
    ai_polished: bool
    ai_polish_content: str | None = None
    ai_polish_at: datetime | None = None
    ai_polish_model: str | None = None
    total_face_value: float
    create_time: datetime
    items: list[ProposalItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
