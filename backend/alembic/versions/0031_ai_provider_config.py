"""AI 配置中心：供应商配置表 + ai:config 权限码。

``ai_provider_config`` 是覆盖层：行不存在/字段为空时各消费方回落到环境
变量，因此历史部署升级后无需立即填库即可继续运行。权限码与
``app/scripts/seed_data.py``、``0004_seed_data.py`` 三处保持一致。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_ai_provider_config"
down_revision: str | None = "0030_content_dna_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_PERMISSIONS = [
    ("ai:config", "AI 配置管理", "ai", "config", "write"),
]


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    bind = op.get_bind()
    if not _inspector().has_table("ai_provider_config"):
        op.create_table(
            "ai_provider_config",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("scope", sa.String(32), nullable=False),
            sa.Column("label", sa.String(64), nullable=False, server_default=sa.text("''")),
            sa.Column("api_url", sa.String(512), nullable=True),
            sa.Column("api_key", sa.Text(), nullable=True),
            sa.Column("chat_model", sa.String(128), nullable=True),
            sa.Column("chat_models", sa.Text(), nullable=True),
            sa.Column("embedding_model", sa.String(128), nullable=True),
            sa.Column("embedding_api_url", sa.String(512), nullable=True),
            sa.Column("embedding_api_key", sa.Text(), nullable=True),
            sa.Column("timeout_seconds", sa.String(16), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.UniqueConstraint("scope", name="uq_ai_provider_config_scope"),
        )

    for code, name, resource, action, ptype in NEW_PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO permission (id, code, name, resource, action, type, "
                "create_time, update_time, is_deleted) "
                "SELECT gen_random_uuid(), :code, :name, :resource, :action, :type, "
                "now(), now(), false "
                "WHERE NOT EXISTS (SELECT 1 FROM permission WHERE code = :code)"
            ),
            {"code": code, "name": name, "resource": resource, "action": action, "type": ptype},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM permission WHERE code = 'ai:config'"))
    op.drop_table("ai_provider_config")
