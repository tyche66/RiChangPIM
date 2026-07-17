from uuid import UUID

from pydantic import BaseModel


class TopAccessedItem(BaseModel):
    share_id: str
    proposal_name: str | None = None
    access_count: int


class ShareStatResponse(BaseModel):
    total_shares: int
    total_access: int
    active_shares: int
    top_accessed: list[TopAccessedItem]


class HotProductItem(BaseModel):
    product_id: UUID
    product_name: str | None = None
    ref_count: int


class HotProductResponse(BaseModel):
    items: list[HotProductItem]


__all__ = ["TopAccessedItem", "ShareStatResponse", "HotProductItem", "HotProductResponse"]
