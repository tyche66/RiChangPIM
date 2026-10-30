"""产品交货期、图片视觉标签与视觉模型配置

* ``product.delivery_period``：供选品按交期展示/筛选，导入导出模板同步；
* ``product_image.vision_tags``：视觉模型从产品图产出的标签，参与产品卡片
  建向量；NULL 表示未标注，与「标注过但为空」区分；
* ``ai_provider_config.vision_model``：视觉标注用的模型名（覆盖层，空则回落
  环境变量 ``AI_VISION_MODEL``）。

Revision ID: 0036_product_delivery_period_vision_tags
Revises: 0035_knowledge_chunk_partial_unique
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0036_product_delivery_period_vision_tags"
down_revision: str | None = "0035_knowledge_chunk_partial_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column("delivery_period", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "product_image",
        sa.Column("vision_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "ai_provider_config",
        sa.Column("vision_model", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_provider_config", "vision_model")
    op.drop_column("product_image", "vision_tags")
    op.drop_column("product", "delivery_period")
