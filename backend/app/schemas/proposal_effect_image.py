from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProposalEffectImageBase(BaseModel):
    """方案效果图基础字段。产品/空间绑定相互独立、均可空；都不设置时作为
    「方案整体」效果图（效果图优先服务方案本身）。"""

    name: str = Field(..., max_length=128, description="展示名，如「客厅全景效果图」")
    product_id: UUID | None = None
    project_space_id: UUID | None = None
    floor_label: str | None = Field(None, max_length=128)
    space_label: str | None = Field(None, max_length=128)
    sort: int = 0

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("效果图名称不可为空")
        return v

    @field_validator("floor_label", "space_label")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ProposalEffectImageCreate(ProposalEffectImageBase):
    """仅需 attachment_id：图片必须先经 /files/upload 落到媒体库。"""

    attachment_id: UUID


class ProposalEffectImageBatchCreate(BaseModel):
    """新增方案对话框一次绑定多张时使用。"""

    items: list[ProposalEffectImageCreate]

    @field_validator("items")
    @classmethod
    def not_empty(
        cls, v: list[ProposalEffectImageCreate]
    ) -> list[ProposalEffectImageCreate]:
        if not v:
            raise ValueError("效果图列表不可为空")
        return v


class ProposalEffectImageUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    product_id: UUID | None = None
    project_space_id: UUID | None = None
    floor_label: str | None = Field(None, max_length=128)
    space_label: str | None = Field(None, max_length=128)
    sort: int | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("效果图名称不可为空")
        return v

    @field_validator("floor_label", "space_label")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ProposalEffectImageResponse(BaseModel):
    id: UUID
    proposal_id: UUID
    project_id: UUID | None = None
    attachment_id: UUID
    name: str
    product_id: UUID | None = None
    project_space_id: UUID | None = None
    floor_label: str | None = None
    space_label: str | None = None
    sort: int = 0
    file_name: str
    file_type: str
    file_size: int
    image_url: str
    # 绑定产品冗余展示字段（绑定的是具体产品，名称随产品实时变化，非快照）
    product_no: str | None = None
    product_name: str | None = None
    create_time: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "ProposalEffectImageBatchCreate",
    "ProposalEffectImageCreate",
    "ProposalEffectImageResponse",
    "ProposalEffectImageUpdate",
]