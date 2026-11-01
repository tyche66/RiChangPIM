"""system_setting 单行表（FR-3 全局设置）

Revision ID: 0039_system_setting
Revises: 0038_share_password_hash
Create Date: 2026-11-01
"""

import json
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0039_system_setting"
down_revision: str | None = "0038_share_password_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 app/schemas/system_setting.py 的默认值保持一致（迁移内联，不 import app 代码）。
DEFAULT_DATA = {
    "brand": {
        "site_name": "RiChangPIM",
        "portal_title": "RiChangPIM Portal",
        "portal_subtitle": (
            "内部只读 AI 工作台。产品、资料和质量记录统一走 Knowledge Gateway，"
            "答案都带引用来源。"
        ),
        "footer_text": "由 RiChangPIM 提供",
        "logo_attachment_id": None,
    },
    "share": {
        "share_default_expire_hours": 24,
        "share_default_max_access_count": 100,
        "share_default_require_password": False,
    },
    "business": {
        "quotation_default_tax_rate": 0.13,
        "amount_decimal_places": 2,
        "currency_symbol": "¥",
    },
}


def upgrade() -> None:
    op.create_table(
        "system_setting",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("data", JSONB(astext_type=sa.Text()), nullable=False),
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
    )
    # 单行表守卫：只允许一行活跃数据（软删除的行不占坑）。
    op.execute(
        "CREATE UNIQUE INDEX ux_system_setting_singleton "
        "ON system_setting ((TRUE)) WHERE is_deleted = FALSE"
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO system_setting (id, data) VALUES (:id, CAST(:data AS JSONB))"
        ),
        {"id": str(uuid4()), "data": json.dumps(DEFAULT_DATA, ensure_ascii=False)},
    )


def downgrade() -> None:
    op.drop_index("ux_system_setting_singleton", table_name="system_setting")
    op.drop_table("system_setting")
