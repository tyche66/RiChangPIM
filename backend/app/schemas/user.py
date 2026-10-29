from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    password: str
    role_id: UUID


class UserUpdate(BaseModel):
    email: str | None = None
    phone: str | None = None
    role_id: UUID | None = None
    status: str | None = None


class ResetPasswordRequest(BaseModel):
    # bcrypt 只取前 72 字节，超出部分会被静默忽略，这里直接拒绝。
    new_password: str = Field(min_length=8, max_length=72)


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
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
