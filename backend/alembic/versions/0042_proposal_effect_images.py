"""proposal_effect_image 方案效果图

方案效果图绑定表：媒体库附件与方案的绑定关系，并可选绑定方案内的某个
产品或某个空间（product_id / project_space_id 相互独立可同时绑定，也允许
都不绑定作为「方案整体」效果图——效果图优先服务方案本身）。

图片本体仍在媒体库（MinIO + attachment 行），本表只记录「属于哪个方案 /
哪个项目、以什么名字展示、是否挂产品/空间、排第几」。删除本行即解除绑定，
附件仍留在媒体库。

Revision ID: 0042_proposal_effect_images
Revises: 0041_proposal_item_display_name
Create Date: 2026-11-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0042_proposal_effect_images"
down_revision: str | None = "0041_proposal_item_display_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def upgrade() -> None:
    if _has_table("proposal_effect_image"):
        return

    op.create_table(
        "proposal_effect_image",
        sa.Column(
            "id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "proposal_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("proposal.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "attachment_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("attachment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "product_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("product.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_space_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("project_spaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("floor_label", sa.String(128), nullable=True),
        sa.Column("space_label", sa.String(128), nullable=True),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("char_length(name) > 0", name="ck_pei_name"),
    )

    op.create_index(
        "ix_pei_proposal",
        "proposal_effect_image",
        ["proposal_id", "sort"],
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "ix_pei_project",
        "proposal_effect_image",
        ["project_id"],
        postgresql_where=sa.text("is_deleted = false AND project_id IS NOT NULL"),
    )
    op.create_index(
        "ix_pei_attachment",
        "proposal_effect_image",
        ["attachment_id"],
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "ix_pei_product",
        "proposal_effect_image",
        ["product_id"],
        postgresql_where=sa.text("is_deleted = false AND product_id IS NOT NULL"),
    )
    op.create_index(
        "uq_pei_proposal_attachment",
        "proposal_effect_image",
        ["proposal_id", "attachment_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    if not _has_table("proposal_effect_image"):
        return
    op.drop_table("proposal_effect_image")