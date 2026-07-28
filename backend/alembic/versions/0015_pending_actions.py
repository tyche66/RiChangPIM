"""pending_actions

Revision ID: 0015_pending_actions
Revises: 0014_knowledge_tables
Create Date: 2026-07-26 00:00:00.000000
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

revision: str = "0015_pending_actions"
down_revision: Union[str, None] = "0014_knowledge_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSIONS = [
    ("ai:pending_action", "AI 待确认动作", "ai", "pending_action", "write"),
]


def upgrade() -> None:
    op.create_table(
        "pending_action",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("generation_version", sa.String(length=32), nullable=False, server_default="p3.1"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.ForeignKeyConstraint(["confirmed_by"], ["user.id"]),
        sa.CheckConstraint(
            "action_type IN ('proposal.create_draft', 'proposal.update_draft')",
            name="check_pending_action_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'expired', 'conflict')",
            name="check_pending_action_status",
        ),
    )
    op.create_index(
        "idx_pending_action_idempotency_active",
        "pending_action",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index("idx_pending_action_status_expires", "pending_action", ["status", "expires_at"])
    op.create_index("idx_pending_action_created_by", "pending_action", ["created_by"])
    op.add_column("proposal", sa.Column("ai_generation_version", sa.String(length=32), nullable=True))
    op.add_column("proposal", sa.Column("ai_source_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("proposal", sa.Column("ai_confirmed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_proposal_ai_confirmed_by_user", "proposal", "user", ["ai_confirmed_by"], ["id"])

    bind = op.get_bind()
    for perm_code, perm_name, resource, action, ptype in PERMISSIONS:
        bind.execute(
            text(
                """
                INSERT INTO permission (id, perm_code, perm_name, resource, action, type, create_time, update_time, is_deleted)
                SELECT :id, :perm_code, :perm_name, :resource, :action, :type, now(), now(), false
                WHERE NOT EXISTS (SELECT 1 FROM permission WHERE perm_code = :perm_code AND is_deleted = false)
                """
            ),
            {"id": str(uuid4()), "perm_code": perm_code, "perm_name": perm_name, "resource": resource, "action": action, "type": ptype},
        )
        for role_code in ("admin", "sales"):
            bind.execute(
                text(
                    """
                    INSERT INTO role_permission (id, role_id, permission_id, create_time, update_time, is_deleted)
                    SELECT :id, r.id, p.id, now(), now(), false
                    FROM role r, permission p
                    WHERE r.role_code = :role_code AND p.perm_code = :perm_code
                      AND r.is_deleted = false AND p.is_deleted = false
                      AND NOT EXISTS (
                        SELECT 1 FROM role_permission rp
                        WHERE rp.role_id = r.id AND rp.permission_id = p.id AND rp.is_deleted = false
                      )
                    """
                ),
                {"id": str(uuid4()), "role_code": role_code, "perm_code": perm_code},
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DELETE FROM role_permission rp USING permission p WHERE rp.permission_id = p.id AND p.perm_code = 'ai:pending_action'"))
    bind.execute(text("DELETE FROM permission WHERE perm_code = 'ai:pending_action'"))
    op.drop_constraint("fk_proposal_ai_confirmed_by_user", "proposal", type_="foreignkey")
    op.drop_column("proposal", "ai_confirmed_by")
    op.drop_column("proposal", "ai_source_ids")
    op.drop_column("proposal", "ai_generation_version")
    op.drop_index("idx_pending_action_created_by", table_name="pending_action")
    op.drop_index("idx_pending_action_status_expires", table_name="pending_action")
    op.drop_index("idx_pending_action_idempotency_active", table_name="pending_action")
    op.drop_table("pending_action")
