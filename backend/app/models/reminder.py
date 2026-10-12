"""提醒与通知模型（HLD §4.13）。

对应迁移 0022（reminders / notifications）。提醒为事务内创建 + 轮询派发
（§10.1，不引入 Celery/outbox）；worker 每 60s 扫 pending/snozed 且到期者，
FOR UPDATE SKIP LOCKED LIMIT 100，经 dedupe_key 幂等。
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.models.base import CommonBase


class Reminder(CommonBase):
    __tablename__ = "reminders"

    rule_code = Column(String(32), nullable=False)
    target_type = Column(String(24), nullable=False)  # content_item | publication | follow_up
    target_id = Column(PGUUID(as_uuid=True), nullable=False)
    assignee_id = Column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    dedupe_key = Column(String(160), nullable=False)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)
    fired_at = Column(DateTime(timezone=True), nullable=True)
    done_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    escalated = Column(Boolean, nullable=False, default=False)
    payload = Column(JSONB, nullable=False, default=dict)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','sent','done','snoozed','cancelled','overdue')",
            name="ck_rm_status",
        ),
        Index(
            "uq_rm_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_rm_due",
            "due_at",
            postgresql_where=text("is_deleted = false AND status IN ('pending','snoozed')"),
        ),
        Index(
            "ix_rm_inbox",
            "assignee_id",
            "status",
            "due_at",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class Notification(CommonBase):
    __tablename__ = "notifications"

    user_id = Column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    kind = Column(String(16), nullable=False, default="reminder")
    link = Column(String(512), nullable=True)
    reminder_id = Column(
        PGUUID(as_uuid=True), ForeignKey("reminders.id", ondelete="SET NULL"), nullable=True
    )
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('reminder','escalation','system')",
            name="ck_nt_kind",
        ),
        Index(
            "ix_nt_inbox",
            "user_id",
            "read_at",
            "create_time",
            postgresql_where=text("is_deleted = false"),
        ),
    )
