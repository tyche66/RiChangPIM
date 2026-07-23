from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProductImageInfo(BaseModel):
    id: UUID
    attachment_id: UUID
    file_url: str
    file_name: str
    file_type: str
    sort: int
    is_cover: bool

    model_config = ConfigDict(from_attributes=True)


class SceneImageInfo(BaseModel):
    id: UUID
    name: str
    attachment_id: UUID
    file_url: str
    file_name: str
    sort: int

    model_config = ConfigDict(from_attributes=True)


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
    description: str | None = None
    specification: str | None = None
    colors: str | None = None
    data_source: str | None = None
    completeness_status: str = "complete"
    tag_ids: list[UUID] = []

    @model_validator(mode="after")
    def validate_placeholder_price(self):
        if self.face_price == 99999 and self.completeness_status != "pending":
            raise ValueError("占位面价 99999 仅允许用于待补充产品")
        return self


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
    description: str | None = None
    specification: str | None = None
    colors: str | None = None
    data_source: str | None = None
    completeness_status: str | None = None
    tag_ids: list[UUID] | None = None

    @field_validator("face_price")
    @classmethod
    def face_price_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("面价不可为空，待核价时请使用 99999")
        return value


class ProductResponse(ProductBase):
    id: UUID
    create_time: datetime
    update_time: datetime
    brand_name: str | None = None
    category_name: str | None = None
    supplier_name: str | None = None
    supplier_id: UUID | None = None
    cost_price: float | None = None
    margin: float | None = None
    profit: float | None = None
    tags: list[str] = []
    images: list[ProductImageInfo] = []
    cover_image_id: UUID | None = None
    cover_image_url: str | None = None
    cover_image_filename: str | None = None
    scene_images: list[SceneImageInfo] = []

    @field_validator("tags", mode="before")
    @classmethod
    def serialize_tag_names(cls, value):
        if not value:
            return []
        return [
            item if isinstance(item, str) else getattr(item, "tag_name", str(item))
            for item in value
        ]

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
    tag_name: str = Field(min_length=1)
    tag_type: str | None = None


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    id: UUID
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductCloneResponse(ProductResponse):
    pass
