from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    product_no: str
    product_name: str
    brand_id: UUID
    supplier_id: UUID
    category_id: UUID
    face_price: float = Field(ge=0)
    cost_price: float | None = None
    material: str | None = None
    stock_status: str = "in_stock"
    status: str = "draft"
    tag_ids: list[UUID] = []


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    product_name: str | None = None
    brand_id: UUID | None = None
    supplier_id: UUID | None = None
    category_id: UUID | None = None
    face_price: float | None = None
    cost_price: float | None = None
    material: str | None = None
    stock_status: str | None = None
    status: str | None = None
    tag_ids: list[UUID] | None = None


class ProductResponse(ProductBase):
    id: UUID
    create_time: datetime
    update_time: datetime
    brand_name: str | None = None
    category_name: str | None = None
    tags: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class CategoryBase(BaseModel):
    category_name: str
    parent_id: UUID | None = None
    sort: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    category_name: str | None = None
    parent_id: UUID | None = None
    sort: int | None = None


class CategoryResponse(CategoryBase):
    id: UUID
    level: int
    children: list["CategoryResponse"] = []
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)


class BrandBase(BaseModel):
    brand_name: str
    logo_url: str | None = None
    description: str | None = None


class BrandCreate(BrandBase):
    pass


class BrandResponse(BrandBase):
    id: UUID
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplierBase(BaseModel):
    supplier_name: str
    contact: str | None = None
    phone: str | None = None
    cooperation_status: str = "active"


class SupplierCreate(SupplierBase):
    pass


class SupplierResponse(SupplierBase):
    id: UUID
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)


class TagBase(BaseModel):
    tag_name: str
    tag_type: str | None = None


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    id: UUID
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductCloneResponse(ProductResponse):
    pass
