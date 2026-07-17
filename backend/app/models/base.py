from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import declared_attr

from app.core.database import Base


class CommonBase(AsyncAttrs, Base):
    __abstract__ = True

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    create_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    update_time = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
