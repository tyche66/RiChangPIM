"""proposal_floor_plans

Track D：方案平面图。媒体库附件与方案的绑定关系。

``proposal_floor_plan``：图片本体仍在媒体库（MinIO + attachment 行），本表只
记录「属于哪个方案 / 哪个项目、以什么名字展示、排第几」。新增列全部可空或
有服务端默认值，旧方案无需回填。

Revision ID: 0032_proposal_floor_plans
Revises: 0031_ai_provider_config
Create Date: 2026-10-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0032_proposal_floor_plans"
down_revision: Union[str, None] = "0031_ai_provider_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_index(table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in _inspector().get_indexes(table))


def upgrade() -> None:
    if _has_table("proposal_floor_plan"):
        return

    op.create_table(
        "proposal_floor_plan",
        sa.Column(
            "id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
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
        sa.Column("floor_label", sa.String(128), nullable=True),
        sa.Column("space_label", sa.String(128), nullable=True),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("char_length(name) > 0", name="ck_pfp_name"),
    )

    op.create_index(
        "ix_pfp_proposal",
        "proposal_floor_plan",
        ["proposal_id", "sort"],
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "ix_pfp_project",
        "proposal_floor_plan",
        ["project_id"],
        postgresql_where=sa.text("is_deleted = false AND project_id IS NOT NULL"),
    )
    op.create_index(
        "ix_pfp_attachment",
        "proposal_floor_plan",
        ["attachment_id"],
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "uq_pfp_proposal_attachment",
        "proposal_floor_plan",
        ["proposal_id", "attachment_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    if not _has_table("proposal_floor_plan"):
        return
    for index in (
        "uq_pfp_proposal_attachment",
        "ix_pfp_attachment",
        "ix_pfp_project",
        "ix_pfp_proposal",
    ):
        if _has_index("proposal_floor_plan", index):
            op.drop_index(index, table_name="proposal_floor_plan")
    op.drop_table("proposal_floor_plan")
