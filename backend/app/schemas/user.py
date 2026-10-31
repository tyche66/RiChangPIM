from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import ensure_bcrypt_compatible


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    user_id: UUID | None = None
    role_code: str | None = None


class UserBase(BaseModel):
    username: str
    email: str | None = None
    phone: str | None = None


class UserCreate(UserBase):
    password: str = Field(min_length=12, max_length=72)
    role_id: UUID

    @field_validator("password")
    @classmethod
    def _password_bytes(cls, value: str) -> str:
        return ensure_bcrypt_compatible(value)


class UserUpdate(BaseModel):
    email: str | None = None
    phone: str | None = None
    role_id: UUID | None = None
    status: Literal["active", "disabled"] | None = None


class ResetPasswordRequest(BaseModel):
    # bcrypt 只取前 72 字节，超出部分会被静默忽略，这里直接拒绝。
    new_password: str = Field(min_length=12, max_length=72)

    @field_validator("new_password")
    @classmethod
    def _password_bytes(cls, value: str) -> str:
        return ensure_bcrypt_compatible(value)


class UserResponse(UserBase):
    id: UUID
    status: str
    role_id: UUID
    last_login_time: datetime | None = None
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)


class RoleBase(BaseModel):
    role_name: str
    role_code: str
    description: str | None = None


class RoleCreate(RoleBase):
    # Frontend sends backend permission codes (for example, "product:view").
    # UUID strings are also accepted by the API for compatibility with DB ids.
    permission_ids: list[str] | None = []


class RoleResponse(RoleBase):
    id: UUID
    permission_ids: list[str] = []
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)


class PermissionBase(BaseModel):
    perm_code: str
    perm_name: str
    resource: str
    action: str
    type: str


class PermissionResponse(PermissionBase):
    id: UUID
    create_time: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def _password_bytes(cls, value: str) -> str:
        return ensure_bcrypt_compatible(value)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(max_length=72)
    new_password: str = Field(min_length=12, max_length=72)

    @field_validator("old_password", "new_password")
    @classmethod
    def _password_bytes(cls, value: str) -> str:
        return ensure_bcrypt_compatible(value)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=4096)
