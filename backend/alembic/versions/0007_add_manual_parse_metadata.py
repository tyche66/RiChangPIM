"""add_manual_parse_metadata

Revision ID: 0007_add_manual_parse_metadata
Revises: 0006_add_manual_indexing
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_add_manual_parse_metadata"
down_revision: Union[str, None] = "0006_add_manual_indexing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_manual",
        sa.Column("parse_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column("product_manual", sa.Column("parse_error", sa.Text(), nullable=True))
    op.add_column("product_manual", sa.Column("parser_name", sa.String(64), nullable=True))
    op.add_column("product_manual", sa.Column("parser_version", sa.String(32), nullable=True))
    op.add_column("product_manual", sa.Column("page_count", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "check_product_manual_parse_status",
        "product_manual",
        "parse_status IN ('pending', 'processing', 'parsed', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("check_product_manual_parse_status", "product_manual", type_="check")
    op.drop_column("product_manual", "page_count")
    op.drop_column("product_manual", "parser_version")
    op.drop_column("product_manual", "parser_name")
    op.drop_column("product_manual", "parse_error")
    op.drop_column("product_manual", "parse_status")
