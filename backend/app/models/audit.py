from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from app.core.database import Base


class Share(Base):
    __tablename__ = "share"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    share_type = Column(String(20), nullable=False)
    target_id = Column(PGUUID(as_uuid=True), nullable=False)
    creator_id = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    status = Column(String(20), default="active")
    create_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    update_time = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)

    creator = relationship("User")
    tokens = relationship("ShareToken", back_populates="share", cascade="all, delete-orphan")


class ShareToken(Base):
    __tablename__ = "share_token"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    share_id = Column(PGUUID(as_uuid=True), ForeignKey("share.id"), nullable=False)
    token = Column(String(64), nullable=False)
    password = Column(String(255))
    expire_time = Column(DateTime(timezone=True))
    max_access_count = Column(Integer)
    current_access_count = Column(Integer, default=0)
    status = Column(String(20), default="active")
    create_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    update_time = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        # 软删除语义：仅对未删除行保证 token 唯一，删除/失效后令牌可被复用。
        Index(
            "idx_share_token_token",
            "token",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    share = relationship("Share", back_populates="tokens")
    logs = relationship("ShareLog", back_populates="token")


class ShareLog(Base):
    __tablename__ = "share_log"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    share_token_id = Column(PGUUID(as_uuid=True), ForeignKey("share_token.id"), nullable=False)
    visitor_id = Column(PGUUID(as_uuid=True), ForeignKey("visitor.id"))
    visitor_ip = Column(String(64))
    visitor_ua = Column(String(512))
    device_fingerprint = Column(String(128))
    openid = Column(String(64))
    access_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    access_result = Column(String(20), nullable=False)

    token = relationship("ShareToken", back_populates="logs")
    visitor = relationship("Visitor", back_populates="logs")


class Visitor(Base):
    __tablename__ = "visitor"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    fingerprint = Column(String(128))
    openid = Column(String(64), unique=True)
    unionid = Column(String(64))
    nickname = Column(String(128))
    avatar_url = Column(String(512))
    first_seen_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    update_time = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    logs = relationship("ShareLog", back_populates="visitor")


class OperationLog(Base):
    __tablename__ = "operation_log"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("user.id"))
    module = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)
    target_id = Column(PGUUID(as_uuid=True))
    request_body = Column(Text)
    response_code = Column(Integer, nullable=False)
    ip = Column(String(64))
    operate_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIConversation(Base):
    __tablename__ = "ai_conversation"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(String(64), nullable=False)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("user.id"))
    question = Column(Text, nullable=False)
    answer = Column(Text)
    sources = Column(Text)
    tool_calls = Column(Text)
    model = Column(String(64), nullable=True)
    token_usage = Column(Text, nullable=True)
    status = Column(String(20), nullable=True, default="completed")
    request_summary = Column(Text, nullable=True)
    response_summary = Column(Text, nullable=True)
    create_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
