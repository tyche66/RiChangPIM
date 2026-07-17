from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.models.base import CommonBase


class Role(CommonBase):
    __tablename__ = "role"

    role_name = Column(String(64), nullable=False)
    role_code = Column(String(32), nullable=False, unique=True)
    description = Column(String(255))

    users = relationship("User", back_populates="role")
    role_permissions = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )


class Permission(CommonBase):
    __tablename__ = "permission"

    perm_code = Column(String(64), nullable=False, unique=True)
    perm_name = Column(String(64), nullable=False)
    resource = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)
    type = Column(String(20), nullable=False)

    role_permissions = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )


class RolePermission(CommonBase):
    __tablename__ = "role_permission"

    role_id = Column(PGUUID(as_uuid=True), ForeignKey("role.id"), nullable=False)
    permission_id = Column(PGUUID(as_uuid=True), ForeignKey("permission.id"), nullable=False)

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


class User(CommonBase):
    __tablename__ = "user"

    username = Column(String(64), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(128))
    phone = Column(String(20))
    status = Column(String(20), default="active")
    role_id = Column(PGUUID(as_uuid=True), ForeignKey("role.id"), nullable=False)
    last_login_time = Column(DateTime(timezone=True))

    role = relationship("Role", back_populates="users")
