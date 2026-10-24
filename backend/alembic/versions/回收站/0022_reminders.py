"""reminders

提醒与通知表：reminders / notifications。

Revision ID: 0022_reminders
Revises: 0021_content_tables
Create Date: 2026-10-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0022_reminders"
down_revision: Union[str, None] = "0021_content_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_index(table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in _inspector().get_indexes(table))


def _create_table_if_missing(name: str, *columns, **kw) -> None:
    """表已存在（例如由 ``create_all`` 建出）时跳过，保证链可在既有库上前进。"""
    if _has_table(name):
        return
    op.create_table(name, *columns, **kw)


def _create_index_if_missing(
    table: str,
    index: str,
    columns: list[str],
    *,
    unique: bool = False,
    where=None,
) -> None:
    if not _has_table(table) or _has_index(table, index):
        return
    op.create_index(index, table, columns, unique=unique, postgresql_where=where)


def upgrade() -> None:
    _create_table_if_missing(
        "reminders",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rule_code", sa.String(32), nullable=False),
        sa.Column("target_type", sa.String(24), nullable=False),
        sa.Column("target_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("assignee_id", PGUUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("dedupe_key", sa.String(160), nullable=False),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("escalated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("payload", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','sent','done','snoozed','cancelled','overdue')",
            name="ck_rm_status",
        ),
    )
    _create_index_if_missing(
        "reminders", "uq_rm_dedupe", ["dedupe_key"], unique=True,
        where=sa.text("is_deleted = false"),
    )
    _create_index_if_missing(
        "reminders", "ix_rm_due", ["due_at"],
        where=sa.text("is_deleted = false AND status IN ('pending','snoozed')"),
    )
    _create_index_if_missing(
        "reminders", "ix_rm_inbox", ["assignee_id", "status", "due_at"],
        where=sa.text("is_deleted = false"),
    )

    _create_table_if_missing(
        "notifications",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("user_id", PGUUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(16), server_default=sa.text("'reminder'"), nullable=False),
        sa.Column("link", sa.String(512), nullable=True),
        sa.Column("reminder_id", PGUUID(as_uuid=True), sa.ForeignKey("reminders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint(
            "kind IN ('reminder','escalation','system')",
            name="ck_nt_kind",
        ),
    )
    _create_index_if_missing(
        "notifications", "ix_nt_inbox", ["user_id", "read_at", "create_time"],
        where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    if _has_table("notifications"):
        op.drop_table("notifications")
    if _has_table("reminders"):
        op.drop_table("reminders")
