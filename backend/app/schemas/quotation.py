from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QuotationItemBase(BaseModel):
    product_id: UUID
    quantity: int = 1
    unit_price: float
    tax_rate: float = 0.13


class QuotationItemCreate(QuotationItemBase):
    pass


class QuotationItemResponse(QuotationItemBase):
    id: UUID
    subtotal: float

    model_config = ConfigDict(from_attributes=True)


class QuotationCreate(BaseModel):
    proposal_id: UUID
    tax_rate: float = 0.13
    discount: float = 1.0
    valid_until: datetime | None = None
    items: list[QuotationItemCreate] = []


class QuotationUpdate(BaseModel):
    tax_rate: float | None = None
    discount: float | None = None
    valid_until: datetime | None = None
    status: str | None = None
    items: list[QuotationItemCreate] | None = None


class QuotationResponse(BaseModel):
    id: UUID
    quotation_no: str
    proposal_id: UUID
    creator_id: UUID
    valid_until: datetime | None = None
    total_amount: float
    subtotal: float
    tax_rate: float
    discount: float
    status: str
    create_time: datetime
    update_time: datetime
    items: list[QuotationItemResponse] = []

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
