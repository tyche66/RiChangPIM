"""项目域 Pydantic schemas（HLD §8.3）。"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    customer_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    code: str | None = Field(None, max_length=32)
    project_type: str = Field("other", max_length=32)
    budget: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    remark: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    code: str | None = Field(None, max_length=32)
    project_type: str | None = Field(None, max_length=32)
    budget: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    remark: str | None = None


class CustomerBrief(BaseModel):
    """设计师可见的客户简要信息（无 PII）。"""

    customer_no: str | None = None
    name: str


class ProjectResponse(BaseModel):
    id: UUID
    customer_id: UUID
    customer_brief: CustomerBrief | None = None
    code: str | None = None
    name: str
    project_type: str
    stage: str
    status: str
    budget: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    remark: str | None = None
    last_activity_at: datetime | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectMemberCreate(BaseModel):
    user_id: UUID
    member_role: str = Field(..., pattern="^(sales|designer|pm|other)$")
    is_primary: bool = False


class ProjectMemberResponse(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    member_role: str
    is_primary: bool
    username: str | None = None
    create_time: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectAssetCreate(BaseModel):
    attachment_id: UUID
    category: str = Field("other", pattern="^(design_drawing|drawing|render|contract|photo|other)$")
    name: str = Field(..., min_length=1, max_length=255)
    remark: str | None = None


class ProjectAssetResponse(BaseModel):
    id: UUID
    project_id: UUID
    category: str
    name: str
    version: int
    is_current: bool
    status: str
    attachment_id: UUID
    remark: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectAssetStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(approved|obsolete)$")


class ProjectStageUpdate(BaseModel):
    to_stage: str
    reason: str | None = None


__all__ = [
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    "CustomerBrief",
    "ProjectMemberCreate",
    "ProjectMemberResponse",
    "ProjectAssetCreate",
    "ProjectAssetResponse",
    "ProjectAssetStatusUpdate",
    "ProjectStageUpdate",
]
