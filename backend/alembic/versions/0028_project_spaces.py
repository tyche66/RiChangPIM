"""project_spaces_and_proposal_space

Track C：方案空间、产品事实快照与客户分享。

* ``project_spaces``：项目空间树（楼层/房间/区域）。
* ``proposal_item`` / ``quotation_item`` 增加
  ``project_space_id`` / ``floor_label`` / ``space_label`` /
  ``material_desc`` / ``product_snapshot``（全部可空，旧数据无需回填）。
* ``product.material_description`` 已在 0026_catalog_attributes 引入，此处不重复。

Revision ID: 0028_project_spaces
Revises: 0027_content_skills
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0028_project_spaces"
down_revision: Union[str, None] = "0027_content_skills"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_index(table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in _inspector().get_indexes(table))


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _inspector().get_columns(table))


def _ensure_table(name: str, *columns, **kw) -> None:
    if _has_table(name):
        return
    op.create_table(name, *columns, **kw)


def _ensure_index(
    table: str, index: str, columns: list[str], *, unique: bool = False, where=None
) -> None:
    if not _has_table(table) or _has_index(table, index):
        return
    op.create_index(index, table, columns, unique=unique, postgresql_where=where)


def _ensure_column(table: str, column: str, type_, **kw) -> None:
    if not _has_table(table) or _has_column(table, column):
        return
    op.add_column(table, sa.Column(column, type_, **kw))


def upgrade() -> None:
    # 1) project_spaces
    _ensure_table(
        "project_spaces",
        sa.Column(
            "id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "project_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("project_spaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("space_type", sa.String(16), server_default=sa.text("'other'"), nullable=False),
        sa.Column("space_name", sa.String(128), nullable=False),
        sa.Column("level", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("space_type IN ('floor','room','zone','other')", name="ck_ps_type"),
        sa.CheckConstraint("level >= 1", name="ck_ps_level"),
    )
    _ensure_index(
        "project_spaces",
        "ix_ps_project",
        ["project_id", "sort"],
        where=sa.text("is_deleted = false"),
    )
    _ensure_index(
        "project_spaces", "ix_ps_parent", ["parent_id"], where=sa.text("is_deleted = false")
    )

    # 2) proposal_item 空间字段 + 产品快照
    for column, type_ in (
        ("project_space_id", PGUUID(as_uuid=True)),
        ("floor_label", sa.String(128)),
        ("space_label", sa.String(128)),
        ("material_desc", sa.Text()),
        ("product_snapshot", JSONB()),
    ):
        _ensure_column("proposal_item", column, type_, nullable=True)
    if _has_table("proposal_item") and _has_column("proposal_item", "project_space_id"):
        # FK 单独加（幂等判断放在约束名上）
        constraint_name = "fk_proposal_item_space"
        existing = {
            fk.get("name")
            for fk in _inspector().get_foreign_keys("proposal_item")
        }
        if constraint_name not in existing:
            op.create_foreign_key(
                constraint_name,
                "proposal_item",
                "project_spaces",
                ["project_space_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # 3) quotation_item 空间字段 + 产品快照
    for column, type_ in (
        ("project_space_id", PGUUID(as_uuid=True)),
        ("floor_label", sa.String(128)),
        ("space_label", sa.String(128)),
        ("material_desc", sa.Text()),
        ("product_snapshot", JSONB()),
    ):
        _ensure_column("quotation_item", column, type_, nullable=True)
    if _has_table("quotation_item") and _has_column("quotation_item", "project_space_id"):
        constraint_name = "fk_quotation_item_space"
        existing = {
            fk.get("name") for fk in _inspector().get_foreign_keys("quotation_item")
        }
        if constraint_name not in existing:
            op.create_foreign_key(
                constraint_name,
                "quotation_item",
                "project_spaces",
                ["project_space_id"],
                ["id"],
                ondelete="SET NULL",
            )

    _ensure_index(
        "proposal_item", "ix_pi_space", ["project_space_id"], where=sa.text("is_deleted = false")
    )
    _ensure_index(
        "quotation_item",
        "ix_qi_space",
        ["project_space_id"],
        where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    for table, index in (
        ("proposal_item", "ix_pi_space"),
        ("quotation_item", "ix_qi_space"),
    ):
        if _has_table(table) and _has_index(table, index):
            op.drop_index(index, table_name=table)
    for table, constraint_name in (
        ("proposal_item", "fk_proposal_item_space"),
        ("quotation_item", "fk_quotation_item_space"),
    ):
        if _has_table(table):
            existing = {fk.get("name") for fk in _inspector().get_foreign_keys(table)}
            if constraint_name in existing:
                op.drop_constraint(constraint_name, table, type_="foreignkey")
    for table in ("proposal_item", "quotation_item"):
        if not _has_table(table):
            continue
        for column in (
            "product_snapshot",
            "material_desc",
            "space_label",
            "floor_label",
            "project_space_id",
        ):
            if _has_column(table, column):
                op.drop_column(table, column)
    if _has_table("project_spaces"):
        op.drop_table("project_spaces")
