"""公告 API 请求模型（FR-4）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Audience = Literal["admin", "portal", "all"]
Level = Literal["info", "important"]


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content_md: str = Field(min_length=1, max_length=20000)
    audience: Audience = "all"
    level: Level = "info"
    enabled: bool = True
    publish_at: datetime | None = None
    expire_at: datetime | None = None

    @model_validator(mode="after")
    def _check_window(self) -> "AnnouncementCreate":
        if self.expire_at and self.publish_at and self.expire_at <= self.publish_at:
            raise ValueError("expire_at 必须晚于 publish_at")
        return self


class AnnouncementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content_md: str | None = Field(default=None, min_length=1, max_length=20000)
    audience: Audience | None = None
    level: Level | None = None
    enabled: bool | None = None
    publish_at: datetime | None = None
    expire_at: datetime | None = None

    @model_validator(mode="after")
    def _check_window(self) -> "AnnouncementUpdate":
        if self.expire_at and self.publish_at and self.expire_at <= self.publish_at:
            raise ValueError("expire_at 必须晚于 publish_at")
        return self
