from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProposalCustomProduct(BaseModel):
    """方案内自定义产品：不入产品库，仅在该方案对外展示。

    字段与产品库产品在方案中的展示字段对齐（名称/面价/规格/材质/颜色/
    材质说明/图片附件）。attachment_id 为媒体库图片，随方案随用随删。
    """

    name: str = Field(..., max_length=255)
    face_price: float | None = Field(None, ge=0)
    material: str | None = Field(None, max_length=128)
    colors: str | None = Field(None, max_length=512)
    specification: str | None = Field(None, max_length=255)
    material_description: str | None = Field(None, max_length=2048)
    attachment_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("自定义产品名称不可为空")
        return v

    @field_validator("material", "colors", "specification", "material_description")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ProposalItemBase(BaseModel):
    product_id: UUID | None = None
    quantity: int = Field(1, ge=1)
    remark: str | None = None
    # Track C：空间归属与材质说明（product_snapshot 由服务端生成，不接受前端传入）
    project_space_id: UUID | None = None
    floor_label: str | None = Field(None, max_length=128)
    space_label: str | None = Field(None, max_length=128)
    material_desc: str | None = None
    # 方案内产品名称：仅服务当前方案，设置后替代产品库名称对外展示
    display_name: str | None = Field(None, max_length=128)
    # 自定义产品（不入产品库）：is_custom=True 时 product_id 必须为空
    is_custom: bool = False
    custom_product: ProposalCustomProduct | None = None

    @field_validator("display_name")
    @classmethod
    def _clean_display_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def _check_bindings(self):
        if self.is_custom:
            if self.product_id is not None:
                raise ValueError("自定义产品不可绑定产品库商品")
            if not self.custom_product or not (self.custom_product.name or "").strip():
                raise ValueError("自定义产品必须填写名称")
        else:
            if self.product_id is None:
                raise ValueError("绑定产品库的规格必须提供 product_id")
        return self


class ProposalItemCreate(ProposalItemBase):
    pass


class ProposalItemResponse(ProposalItemBase):
    id: UUID
    product_no: str | None = None
    product_name: str | None = None
    face_price: float | None = None
    line_total: float
    cover_image_url: str | None = None
    # Track C：产品事实快照（旧方案为 None，读取时回落当前产品字段）
    product_snapshot: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class ProposalBase(BaseModel):
    proposal_name: str
    customer_name: str | None = None
    creator_id: UUID
    # Track C：客户与项目接通（可空，兼容旧方案）
    customer_id: UUID | None = None
    project_id: UUID | None = None


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
    customer_id: UUID | None = None
    project_id: UUID | None = None
    items: list[ProposalItemCreate] | None = None


class ProposalResponse(ProposalBase):
    id: UUID
    proposal_no: str
    status: str
    ai_polished: bool
    ai_polish_content: str | None = None
    ai_polish_at: datetime | None = None
    ai_polish_model: str | None = None
    ai_generation_version: str | None = None
    ai_source_ids: list[str] | None = None
    ai_confirmed_by: UUID | None = None
    total_face_value: float
    create_time: datetime
    items: list[ProposalItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
