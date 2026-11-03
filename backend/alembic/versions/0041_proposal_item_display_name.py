"""proposal_item 增加 display_name（方案内产品名称）

Revision ID: 0041_proposal_item_display_name
Revises: 0040_announcement
Create Date: 2026-11-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_proposal_item_display_name"
down_revision: str | None = "0040_announcement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "display_name" not in {c["name"] for c in inspector.get_columns("proposal_item")}:
        op.add_column(
            "proposal_item",
            sa.Column("display_name", sa.String(length=128), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "display_name" in {c["name"] for c in inspector.get_columns("proposal_item")}:
        op.drop_column("proposal_item", "display_name")