from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PendingActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    action_type: Literal["proposal.create_draft", "proposal.update_draft"]
    idempotency_key: str = Field(min_length=8, max_length=128)
    target_type: str | None = Field(default=None, max_length=32)
    target_id: UUID | None = None
    payload: dict[str, Any]
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    model_provider: str | None = Field(default=None, max_length=64)
    model_name: str | None = Field(default=None, max_length=128)
    generation_version: str = Field(default="p3.1", max_length=32)
    reason: str | None = None
    expires_at: datetime | None = None


class PendingActionConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class PendingActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    action_type: str
    status: str
    idempotency_key: str
    target_type: str | None = None
    target_id: UUID | None = None
    payload: dict[str, Any]
    source_ids: list[str]
    model_provider: str | None = None
    model_name: str | None = None
    generation_version: str
    reason: str | None = None
    result: dict[str, Any] | None = None
    created_by: UUID
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
    expires_at: datetime
    create_time: datetime
