from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuotationItemBase(BaseModel):
    product_id: UUID
    quantity: int = Field(1, ge=1)
    unit_price: float = Field(ge=0)
    tax_rate: float = Field(0.0, ge=0, le=1)


class QuotationItemCreate(QuotationItemBase):
    pass


class QuotationItemResponse(QuotationItemBase):
    id: UUID
    product_no: str
    product_name: str
    face_price: float
    subtotal: float = Field(ge=0)
    cover_image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class QuotationCreate(BaseModel):
    proposal_id: UUID
    tax_rate: float = Field(0.13, ge=0, le=1)
    discount: float = Field(1.0, ge=0, le=1)
    valid_until: datetime | None = None
    items: list[QuotationItemCreate] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list[QuotationItemCreate]) -> list[QuotationItemCreate]:
        if not v:
            raise ValueError("报价明细不可为空")
        return v


class QuotationUpdate(BaseModel):
    tax_rate: float | None = Field(None, ge=0, le=1)
    discount: float | None = Field(None, ge=0, le=1)
    valid_until: datetime | None = None
    status: str | None = None
    items: list[QuotationItemCreate] | None = None


class QuotationResponse(BaseModel):
    id: UUID
    quotation_no: str
    proposal_id: UUID
    proposal_no: str
    proposal_name: str
    creator_id: UUID
    valid_until: datetime | None = None
    total_amount: float
    subtotal: float
    tax_rate: float
    discount: float
    status: str
    create_time: datetime
    update_time: datetime
    items: list[QuotationItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class QuotationPDFResponse(BaseModel):
    task_id: str
    status: str = "pending"
    note: str
    quotation_id: UUID


__all__ = [
    "QuotationItemBase",
    "QuotationItemCreate",
    "QuotationItemResponse",
    "QuotationCreate",
    "QuotationUpdate",
    "QuotationResponse",
    "QuotationPDFResponse",
]
