from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import text

from app.models.base import CommonBase


class PendingAction(CommonBase):
    __tablename__ = "pending_action"

    action_type = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    idempotency_key = Column(String(128), nullable=False)
    target_type = Column(String(32), nullable=True)
    target_id = Column(PGUUID(as_uuid=True), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    source_ids = Column(JSONB, nullable=False, default=list)
    model_provider = Column(String(64), nullable=True)
    model_name = Column(String(128), nullable=True)
    generation_version = Column(String(32), nullable=False, default="p3.1")
    reason = Column(Text, nullable=True)
    result = Column(JSONB, nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    confirmed_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('proposal.create_draft', 'proposal.update_draft')",
            name="check_pending_action_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'expired', 'conflict')",
            name="check_pending_action_status",
        ),
        Index(
            "idx_pending_action_idempotency_active",
            "idempotency_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("idx_pending_action_status_expires", "status", "expires_at"),
        Index("idx_pending_action_created_by", "created_by"),
    )
