"""announcement 表（FR-4 后台可编辑公告）

Revision ID: 0040_announcement
Revises: 0039_system_setting
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0040_announcement"
down_revision: str | None = "0039_system_setting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "announcement",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(length=20), nullable=False, server_default="all"),
        sa.Column("level", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "update_time",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.CheckConstraint(
            "audience IN ('admin', 'portal', 'all')",
            name="check_announcement_audience",
        ),
        sa.CheckConstraint(
            "level IN ('info', 'important')",
            name="check_announcement_level",
        ),
    )
    op.create_index(
        "idx_announcement_audience_enabled",
        "announcement",
        ["audience", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("idx_announcement_audience_enabled", table_name="announcement")
    op.drop_table("announcement")
