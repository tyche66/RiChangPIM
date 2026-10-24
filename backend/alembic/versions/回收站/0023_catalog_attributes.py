"""catalog_attributes

Track A：通用产品属性检索的数据基座。

* ``catalog_attribute_definition`` / ``catalog_attribute_option`` /
  ``catalog_attribute_alias`` / ``product_attribute_value`` 四张受治理属性表。
* ``product.material_description`` 可空字段：材质说明独立于 description。
* 启用 ``pg_trgm`` 扩展并在产品可检索文本列上建 gin_trgm_ops 索引，
  用于中文无空格查询的模糊文本召回（不引入 ES / 独立向量库）。

Revision ID: 0023_catalog_attributes
Revises: 0022_reminders
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0023_catalog_attributes"
down_revision: Union[str, None] = "0022_reminders"
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


def _create_table_if_missing(name: str, *columns, **kw) -> None:
    if _has_table(name):
        return
    op.create_table(name, *columns, **kw)


def _create_index_if_missing(
    table: str,
    index: str,
    columns: list[str],
    *,
    unique: bool = False,
    where=None,
    postgresql_using: str | None = None,
    postgresql_ops: dict[str, str] | None = None,
) -> None:
    if not _has_table(table) or _has_index(table, index):
        return
    if postgresql_ops:
        # trigram 类索引必须显式指定 operator class
        expressions = [
            sa.column(name).op(postgresql_ops.get(name, "gin_trgm_ops"))
            for name in columns
        ]
        op.create_index(
            index, table, expressions, unique=unique, postgresql_where=where,
            postgresql_using=postgresql_using or "gin",
        )
        return
    op.create_index(
        index,
        table,
        columns,
        unique=unique,
        postgresql_where=where,
        postgresql_using=postgresql_using,
    )


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
    # 1) 文本召回基建：pg_trgm（幂等；实例缺扩展时不影响后续 DDL）
    op.get_bind().execute(sa.text('CREATE EXTENSION IF NOT EXISTS pg_trgm'))

    # 2) product.material_description（可空，旧数据可读）
    if _has_table("product") and not _has_column("product", "material_description"):
        op.add_column(
            "product", sa.Column("material_description", sa.Text(), nullable=True)
        )

    # 3) catalog_attribute_definition
    _create_table_if_missing(
        "catalog_attribute_definition",
        *_common_columns(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("data_type", sa.String(16), server_default=sa.text("'option'"), nullable=False),
        sa.Column("multi_value", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("searchable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("hard_filterable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint(
            "data_type IN ('option','text','number','range')", name="ck_cad_type"
        ),
    )
    _create_index_if_missing(
        "catalog_attribute_definition",
        "uq_cad_code",
        ["code"],
        unique=True,
        where=sa.text("is_deleted = false"),
    )
    _create_index_if_missing(
        "catalog_attribute_definition",
        "ix_cad_sort",
        ["sort_order"],
        where=sa.text("is_deleted = false"),
    )

    # 4) catalog_attribute_option
    _create_table_if_missing(
        "catalog_attribute_option",
        *_common_columns(),
        sa.Column(
            "attribute_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("catalog_attribute_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("extra", JSONB(), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
    )
    _create_index_if_missing(
        "catalog_attribute_option",
        "uq_cao_attribute_code",
        ["attribute_id", "code"],
        unique=True,
        where=sa.text("is_deleted = false"),
    )
    _create_index_if_missing(
        "catalog_attribute_option",
        "ix_cao_attribute_sort",
        ["attribute_id", "sort_order"],
        where=sa.text("is_deleted = false"),
    )

    # 5) catalog_attribute_alias
    _create_table_if_missing(
        "catalog_attribute_alias",
        *_common_columns(),
        sa.Column(
            "option_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("catalog_attribute_option.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(128), nullable=False),
        sa.Column("normalized_alias", sa.String(128), nullable=False),
        sa.Column("source", sa.String(32), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.UniqueConstraint("option_id", "normalized_alias", name="uq_caa_option_alias"),
    )
    _create_index_if_missing("catalog_attribute_alias", "ix_caa_norm", ["normalized_alias"])
    _create_index_if_missing(
        "catalog_attribute_alias",
        "ix_caa_option",
        ["option_id"],
        where=sa.text("is_deleted = false"),
    )

    # 6) product_attribute_value
    _create_table_if_missing(
        "product_attribute_value",
        *_common_columns(),
        sa.Column(
            "product_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("product.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "attribute_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("catalog_attribute_definition.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "option_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("catalog_attribute_option.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("value_text", sa.String(255), nullable=True),
        sa.Column("value_num", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column(
            "source", sa.String(32), server_default=sa.text("'manual'"), nullable=False
        ),
        sa.Column("verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_pav_confidence",
        ),
        sa.CheckConstraint(
            "source IN ('manual','business_confirmed','import','ai_inferred','migrated')",
            name="ck_pav_source",
        ),
    )
    _create_index_if_missing(
        "product_attribute_value",
        "uq_pav_product_option",
        ["product_id", "attribute_id", "option_id"],
        unique=True,
        where=sa.text("is_deleted = false AND option_id IS NOT NULL"),
    )
    _create_index_if_missing(
        "product_attribute_value",
        "uq_pav_product_text",
        ["product_id", "attribute_id", "value_text"],
        unique=True,
        where=sa.text("is_deleted = false AND option_id IS NULL"),
    )
    _create_index_if_missing(
        "product_attribute_value",
        "ix_pav_product",
        ["product_id"],
        where=sa.text("is_deleted = false"),
    )
    _create_index_if_missing("product_attribute_value", "ix_pav_attribute", ["attribute_id"])
    _create_index_if_missing("product_attribute_value", "ix_pav_option", ["option_id"])
    _create_index_if_missing(
        "product_attribute_value",
        "ix_pav_number",
        ["attribute_id", "value_num"],
        where=sa.text("is_deleted = false AND value_num IS NOT NULL"),
    )

    # 7) 文本召回索引（幂等；缺 pg_trgm 扩展时跳过）
    if _has_table("product"):
        for name, column in (
            ("idx_product_name_trgm", "product_name"),
            ("idx_product_no_trgm", "product_no"),
            ("idx_product_material_trgm", "material"),
        ):
            if _has_index("product", name):
                continue
            # trigram 索引必须显式 operator class，直接用 DDL 最稳妥
            op.execute(
                sa.text(
                    f'CREATE INDEX IF NOT EXISTS "{name}" '
                    f'ON product USING gin ("{column}" gin_trgm_ops)'
                )
            )

def downgrade() -> None:
    if _has_table("product"):
        for name in ("idx_product_name_trgm", "idx_product_no_trgm", "idx_product_material_trgm"):
            if _has_index("product", name):
                op.drop_index(name, table_name="product")
        if _has_column("product", "material_description"):
            op.drop_column("product", "material_description")
    for table in ("product_attribute_value", "catalog_attribute_alias", "catalog_attribute_option", "catalog_attribute_definition"):
        if _has_table(table):
            op.drop_table(table)
    op.get_bind().execute(sa.text("DROP EXTENSION IF EXISTS pg_trgm"))
