"""content_skills

Track B：内容工坊 Skills 与独立选题。

* ``content_skills``：Skill 定义（topic / content），含启用开关与审计字段。
* ``content_topic_runs`` / ``content_topic_items``：独立选题模块。
* ``content_batches.source_skill_code`` / ``content_items.source_skill_code``：
  可空，用于追溯生成时使用的 Skill（空 = 默认模板）。
* permission 种子新增 ``content:manage``。

Revision ID: 0027_content_skills
Revises: 0026_catalog_attributes
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import text

revision: str = "0027_content_skills"
down_revision: Union[str, None] = "0026_catalog_attributes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 新增权限码（Track B  Skills 管理中心）
NEW_PERMISSIONS = [
    ("content:manage", "内容Skill管理", "content", "manage", "write"),
]

# 角色 -> 权限映射增量（admin 通过 "*" 展开天然包含）
ROLE_PERMISSION_MAP = {
    "admin": ["content:manage"],
}


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_index(table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in _inspector().get_indexes(table))


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _inspector().get_columns(table))


def _create_table_if_missing(name: str, *columns, **kw) -> None:
    if _has_table(name):
        return
    op.create_table(name, *columns, **kw)


def _create_index_if_missing(
    table: str, index: str, columns: list[str], *, unique: bool = False, where=None
) -> None:
    if not _has_table(table) or _has_index(table, index):
        return
    op.create_index(index, table, columns, unique=unique, postgresql_where=where)


def _common_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
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
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def upgrade() -> None:
    # 1) content_skills
    _create_table_if_missing(
        "content_skills",
        *_common_columns(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("skill_type", sa.String(16), server_default=sa.text("'content'"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_template", sa.Text(), nullable=True),
        sa.Column("output_schema", JSONB(), nullable=True),
        sa.Column("prompt_version", sa.String(16), server_default=sa.text("'v1'"), nullable=False),
        sa.Column("supported_platforms", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("skill_type IN ('topic','content')", name="ck_cs_type"),
    )
    _create_index_if_missing(
        "content_skills", "uq_cs_code", ["code"], unique=True, where=sa.text("is_deleted = false")
    )
    _create_index_if_missing(
        "content_skills",
        "ix_cs_type_enabled",
        ["skill_type", "enabled"],
        where=sa.text("is_deleted = false"),
    )
    _create_index_if_missing(
        "content_skills", "ix_cs_sort", ["sort_order"], where=sa.text("is_deleted = false")
    )

    # 2) content_topic_runs
    _create_table_if_missing(
        "content_topic_runs",
        *_common_columns(),
        sa.Column(
            "skill_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("content_skills.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("skill_code", sa.String(64), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("tone", sa.String(32), nullable=True),
        sa.Column("product_ids", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("requested_count", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'running'"), nullable=False),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("model_provider", sa.String(32), nullable=True),
        sa.Column("model_name", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(16), server_default=sa.text("'v1'"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("status IN ('pending','running','done','failed')", name="ck_ctr_status"),
        sa.CheckConstraint("requested_count BETWEEN 1 AND 10", name="ck_ctr_count"),
    )
    _create_index_if_missing(
        "content_topic_runs", "ix_ctr_created", ["create_time"], where=sa.text("is_deleted = false")
    )
    _create_index_if_missing(
        "content_topic_runs", "ix_ctr_skill", ["skill_id"], where=sa.text("is_deleted = false")
    )

    # 3) content_topic_items
    _create_table_if_missing(
        "content_topic_items",
        *_common_columns(),
        sa.Column(
            "run_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("content_topic_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("angle", sa.Text(), nullable=True),
        sa.Column("audience", sa.String(255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("suggested_platform", sa.String(32), nullable=True),
        sa.Column("related_product_ids", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source_skill_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'draft'"), nullable=False),
        sa.Column(
            "adopted_by",
            PGUUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.String(255), nullable=True),
        sa.Column(
            "content_batch_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("content_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("status IN ('draft','adopted','rejected','used')", name="ck_cti_status"),
    )
    _create_index_if_missing(
        "content_topic_items", "ix_cti_run", ["run_id"], where=sa.text("is_deleted = false")
    )
    _create_index_if_missing(
        "content_topic_items",
        "ix_cti_status",
        ["status", "create_time"],
        where=sa.text("is_deleted = false"),
    )

    # 4) 既有表加 source_skill_code（可空，旧数据可读）
    if _has_table("content_batches") and not _has_column("content_batches", "source_skill_code"):
        op.add_column(
            "content_batches", sa.Column("source_skill_code", sa.String(64), nullable=True)
        )
    if _has_table("content_items") and not _has_column("content_items", "source_skill_code"):
        op.add_column(
            "content_items", sa.Column("source_skill_code", sa.String(64), nullable=True)
        )

    # 5) 权限种子（幂等）
    for perm_code, perm_name, resource, action, ptype in NEW_PERMISSIONS:
        op.get_bind().execute(
            text("""
                INSERT INTO permission (id, perm_code, perm_name, resource,
                                        action, type, create_time, update_time, is_deleted)
                SELECT :id, :perm_code, :perm_name, :resource,
                       :action, :type, now(), now(), false
                WHERE NOT EXISTS (
                    SELECT 1 FROM permission
                    WHERE perm_code = :perm_code AND is_deleted = false
                )
            """),
            {
                "id": str(_new_uuid()),
                "perm_code": perm_code,
                "perm_name": perm_name,
                "resource": resource,
                "action": action,
                "type": ptype,
            },
        )

    # 6) 角色-权限映射（幂等）
    for role_code, perm_codes in ROLE_PERMISSION_MAP.items():
        for perm_code in perm_codes:
            op.get_bind().execute(
                text("""
                    INSERT INTO role_permission (id, role_id, permission_id,
                                                 create_time, update_time, is_deleted)
                    SELECT :id, r.id, p.id, now(), now(), false
                    FROM role r, permission p
                    WHERE r.role_code = :role_code
                      AND p.perm_code = :perm_code
                      AND r.is_deleted = false
                      AND p.is_deleted = false
                      AND NOT EXISTS (
                          SELECT 1 FROM role_permission rp
                          WHERE rp.role_id = r.id
                            AND rp.permission_id = p.id
                            AND rp.is_deleted = false
                      )
                """),
                {"id": str(_new_uuid()), "role_code": role_code, "perm_code": perm_code},
            )


def _new_uuid():
    from uuid import uuid4

    return uuid4()


def downgrade() -> None:
    # 权限与映射（先删映射再删权限，避免 FK 违反）
    codes = [p[0] for p in NEW_PERMISSIONS]
    op.get_bind().execute(
        text("""
            DELETE FROM role_permission rp
            USING permission p
            WHERE rp.permission_id = p.id
              AND p.perm_code = ANY(:codes)
        """),
        {"codes": codes},
    )
    op.get_bind().execute(
        text("DELETE FROM permission WHERE perm_code = ANY(:codes)"), {"codes": codes}
    )

    if _has_table("content_items") and _has_column("content_items", "source_skill_code"):
        op.drop_column("content_items", "source_skill_code")
    if _has_table("content_batches") and _has_column("content_batches", "source_skill_code"):
        op.drop_column("content_batches", "source_skill_code")

    for table in ("content_topic_items", "content_topic_runs", "content_skills"):
        if _has_table(table):
            op.drop_table(table)
