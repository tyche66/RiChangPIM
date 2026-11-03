"""proposal_item 支持自定义产品（不入产品库）

方案内自定义产品最小方案：proposal_item 上叠加 is_custom 标志与
custom_product JSONB（name/face_price/material/colors/specification/
material_description/attachment_id）。自定义产品不入产品库，仅在该方案
内展示；product_id 放开非空约束以承载自定义行。

Revision ID: 0043_proposal_item_custom_product
Revises: 0042_proposal_effect_images
Create Date: 2026-11-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0043_proposal_item_custom_product"
down_revision: str | None = "0042_proposal_effect_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("proposal_item")}

    if "is_custom" not in cols:
        op.add_column(
            "proposal_item",
            sa.Column(
                "is_custom",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    if "custom_product" not in cols:
        op.add_column(
            "proposal_item",
            sa.Column("custom_product", JSONB(astext_type=sa.Text()), nullable=True),
        )
    # 自定义产品行不绑定产品库：放开 product_id 非空约束
    if "product_id" in cols:
        op.alter_column(
            "proposal_item",
            "product_id",
            existing_type=PGUUID(as_uuid=True),
            nullable=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("proposal_item")}

    if "is_custom" in cols:
        op.drop_column("proposal_item", "is_custom")
    if "custom_product" in cols:
        op.drop_column("proposal_item", "custom_product")
    if "product_id" in cols:
        op.alter_column(
            "proposal_item",
            "product_id",
            existing_type=PGUUID(as_uuid=True),
            nullable=False,
        )