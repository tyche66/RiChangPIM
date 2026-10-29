from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProposalFloorPlanBase(BaseModel):
    name: str = Field(..., max_length=128, description="展示名，如「江韵方案一层平面图」")
    floor_label: str | None = Field(None, max_length=128)
    space_label: str | None = Field(None, max_length=128)
    sort: int = 0

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("平面图名称不可为空")
        return v

    @field_validator("floor_label", "space_label")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ProposalFloorPlanCreate(ProposalFloorPlanBase):
    """仅需 attachment_id：图片必须先经 /files/upload 落到媒体库。"""

    attachment_id: UUID


class ProposalFloorPlanBatchCreate(BaseModel):
    """新增方案对话框一次绑定多张时使用。"""

    items: list[ProposalFloorPlanCreate]

    @field_validator("items")
    @classmethod
    def not_empty(cls, v: list[ProposalFloorPlanCreate]) -> list[ProposalFloorPlanCreate]:
        if not v:
            raise ValueError("平面图列表不可为空")
        return v


class ProposalFloorPlanUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
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
            raise ValueError("平面图名称不可为空")
        return v

    @field_validator("floor_label", "space_label")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ProposalFloorPlanResponse(BaseModel):
    id: UUID
    proposal_id: UUID
    project_id: UUID | None = None
    attachment_id: UUID
    name: str
    floor_label: str | None = None
    space_label: str | None = None
    sort: int = 0
    file_name: str
    file_type: str
    file_size: int
    image_url: str
    create_time: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "ProposalFloorPlanBatchCreate",
    "ProposalFloorPlanCreate",
    "ProposalFloorPlanResponse",
    "ProposalFloorPlanUpdate",
]
