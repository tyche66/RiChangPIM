from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProposalItemBase(BaseModel):
    product_id: UUID
    quantity: int = 1
    remark: str | None = None


class ProposalItemCreate(ProposalItemBase):
    pass


class ProposalBase(BaseModel):
    proposal_name: str
    customer_name: str | None = None
    creator_id: UUID


class ProposalCreate(ProposalBase):
    items: list[ProposalItemCreate] = []


class ProposalUpdate(BaseModel):
    proposal_name: str | None = None
    customer_name: str | None = None


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
    items: list[ProposalItemBase] = []

    model_config = ConfigDict(from_attributes=True)
