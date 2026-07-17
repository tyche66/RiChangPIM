"""sunon_pilot_product_fields

Revision ID: 0009_sunon_pilot_product_fields
Revises: 0008_v11_audit_workflow_ocr
Create Date: 2026-07-17
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0009_sunon_pilot_product_fields"
down_revision: str | None = "0008_v11_audit_workflow_ocr"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("product", sa.Column("specification", sa.String(255), nullable=True))
    op.add_column("product", sa.Column("colors", sa.Text(), nullable=True))
    op.add_column("product", sa.Column("data_source", sa.String(512), nullable=True))
    op.add_column(
        "product",
        sa.Column("completeness_status", sa.String(20), nullable=False, server_default="complete"),
    )
    op.create_check_constraint(
        "check_product_completeness_status",
        "product",
        "completeness_status IN ('complete', 'pending', 'unknown')",
    )
    op.create_check_constraint(
        "check_product_placeholder_price",
        "product",
        "face_price <> 99999 OR completeness_status = 'pending'",
    )
    op.drop_constraint("check_product_stock_status", "product", type_="check")
    op.create_check_constraint(
        "check_product_stock_status",
        "product",
        "stock_status IN ('in_stock', 'out_of_stock', 'preorder', 'unknown')",
    )


def downgrade() -> None:
    op.execute("UPDATE product SET stock_status = 'in_stock' WHERE stock_status = 'unknown'")
    op.drop_constraint("check_product_placeholder_price", "product", type_="check")
    op.drop_constraint("check_product_completeness_status", "product", type_="check")
    op.drop_column("product", "completeness_status")
    op.drop_column("product", "data_source")
    op.drop_column("product", "colors")
    op.drop_column("product", "specification")
    op.drop_constraint("check_product_stock_status", "product", type_="check")
    op.create_check_constraint(
        "check_product_stock_status",
        "product",
        "stock_status IN ('in_stock', 'out_of_stock', 'preorder')",
    )
