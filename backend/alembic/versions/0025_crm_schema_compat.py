"""crm_schema_compat

CRM 明细表补齐（幂等）。

背景：生产运行镜像的迁移链以 ``0019_crm_base_tables`` 只建 customers / projects，
其余 CRM 明细表（project_members / entity_stage_logs / customer_dialogues /
customer_dialogue_attachments / requirements / follow_ups / project_assets）
由启动时 ``Base.metadata.create_all`` 补建，从未纳入受版本管理的链。本迁移把
这些表纳入 0018-0024（生产基线）之后的连续链，DDL 与原本地 ``0019_crm_detail``
一致（customers / projects 除外——已由生产 ``0019_crm_base_tables`` 建立）。

设计约束：
  * 所有 DDL 均幂等（表/索引存在即跳过），可与 create_all 或生产既有 schema 共存。
  * proposal.customer_id / project_id 列与外键、attachment.biz_domain /
    biz_scope_id 已由生产 ``0023_crm_sales_links_compat`` /
    ``0024_attachment_biz_domain_compat`` 处理，此处不重复。
  * ``downgrade`` 仅删本迁移真正可能拥有的对象，customers / projects 不动。

Revision ID: 0025_crm_schema_compat
Revises: 0024_attachment_biz_domain_compat
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0025_crm_schema_compat"
down_revision: Union[str, None] = "0024_attachment_biz_domain_compat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_index(table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in _inspector().get_indexes(table))


def _common_columns() -> tuple[sa.Column, ...]:
    """与 ``app.models.base.CommonBase`` 对齐的公共列。"""
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


def upgrade() -> None:
    # customers / projects 已由 0019_crm_base_tables 建立；此处只补明细表。

    # 1) project_members
    _create_table_if_missing(
        "project_members",
        *_common_columns(),
        sa.Column("project_id", PGUUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", PGUUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("member_role", sa.String(20), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("member_role IN ('sales','designer','pm','other')", name="ck_pm_role"),
    )
    _create_index_if_missing("project_members", "uq_pm_project_user_role", ["project_id", "user_id", "member_role"], unique=True, where=sa.text("is_deleted = false"))
    _create_index_if_missing("project_members", "uq_pm_primary", ["project_id", "member_role"], unique=True, where=sa.text("is_deleted = false AND is_primary = true"))
    _create_index_if_missing("project_members", "ix_pm_user", ["user_id"], where=sa.text("is_deleted = false"))

    # 2) entity_stage_logs
    _create_table_if_missing(
        "entity_stage_logs",
        *_common_columns(),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("from_stage", sa.String(20), nullable=False),
        sa.Column("to_stage", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("operator_id", PGUUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("entity_type IN ('customer','project')", name="ck_esl_entity_type"),
    )
    _create_index_if_missing("entity_stage_logs", "ix_esl_entity", ["entity_type", "entity_id", "create_time"], where=sa.text("is_deleted = false"))

    # 3) customer_dialogues
    _create_table_if_missing(
        "customer_dialogues",
        *_common_columns(),
        sa.Column("customer_id", PGUUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", PGUUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("channel", sa.String(32), server_default=sa.text("'wechat'"), nullable=False),
        sa.Column("direction", sa.String(8), server_default=sa.text("'in'"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("channel IN ('wechat','phone','visit','sms','other')", name="ck_dlg_channel"),
        sa.CheckConstraint("direction IN ('in','out')", name="ck_dlg_direction"),
        sa.CheckConstraint("char_length(content) <= 20000", name="ck_dlg_len"),
    )
    _create_index_if_missing("customer_dialogues", "ix_dlg_customer_time", ["customer_id", "occurred_at"], where=sa.text("is_deleted = false"))

    # 4) customer_dialogue_attachments
    _create_table_if_missing(
        "customer_dialogue_attachments",
        *_common_columns(),
        sa.Column("dialogue_id", PGUUID(as_uuid=True), sa.ForeignKey("customer_dialogues.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attachment_id", PGUUID(as_uuid=True), sa.ForeignKey("attachment.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sort_no", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
    )
    _create_index_if_missing("customer_dialogue_attachments", "uq_dlg_att", ["dialogue_id", "attachment_id"], unique=True, where=sa.text("is_deleted = false"))

    # 5) requirements
    _create_table_if_missing(
        "requirements",
        *_common_columns(),
        sa.Column("customer_id", PGUUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", PGUUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured", JSONB(), nullable=True),
        sa.Column("source", sa.String(16), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("confirmed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source_action_id", PGUUID(as_uuid=True), sa.ForeignKey("pending_action.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("source IN ('manual','ai_extracted')", name="ck_req_source"),
    )
    _create_index_if_missing("requirements", "ix_req_customer", ["customer_id", "create_time"], where=sa.text("is_deleted = false"))

    # 6) follow_ups
    _create_table_if_missing(
        "follow_ups",
        *_common_columns(),
        sa.Column("customer_id", PGUUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", PGUUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("follower_id", PGUUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("method", sa.String(32), server_default=sa.text("'wechat'"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("result", sa.String(32), nullable=True),
        sa.Column("next_follow_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint(
            "result IS NULL OR result IN ('connected','no_answer','interested','rejected','scheduled','other')",
            name="ck_fu_result",
        ),
    )
    _create_index_if_missing("follow_ups", "ix_fu_customer_time", ["customer_id", "create_time"], where=sa.text("is_deleted = false"))
    _create_index_if_missing("follow_ups", "ix_fu_follower_time", ["follower_id", "create_time"], where=sa.text("is_deleted = false"))
    _create_index_if_missing("follow_ups", "ix_fu_next_pending", ["next_follow_at"], where=sa.text("is_deleted = false AND done_at IS NULL AND next_follow_at IS NOT NULL"))

    # 7) project_assets
    _create_table_if_missing(
        "project_assets",
        *_common_columns(),
        sa.Column("project_id", PGUUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("category", sa.String(20), server_default=sa.text("'other'"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("attachment_id", PGUUID(as_uuid=True), sa.ForeignKey("attachment.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint(
            "category IN ('design_drawing','drawing','render','contract','photo','other')", name="ck_pa_category"
        ),
        sa.CheckConstraint("status IN ('draft','shared','approved','obsolete')", name="ck_pa_status"),
        sa.CheckConstraint("version >= 1", name="ck_pa_version"),
    )
    _create_index_if_missing("project_assets", "uq_pa_pcnv", ["project_id", "category", "name", "version"], unique=True, where=sa.text("is_deleted = false"))
    _create_index_if_missing("project_assets", "uq_pa_current", ["project_id", "category", "name"], unique=True, where=sa.text("is_deleted = false AND is_current = true"))
    _create_index_if_missing("project_assets", "ix_pa_project", ["project_id"], where=sa.text("is_deleted = false"))

    # proposal.customer_id / project_id 列、外键与索引由 0023_crm_sales_links_compat
    # 处理（且生产库已应用）；此处不再创建本地旧命名的重复外键。


def downgrade() -> None:
    for table in (
        "project_assets",
        "follow_ups",
        "requirements",
        "customer_dialogue_attachments",
        "customer_dialogues",
        "entity_stage_logs",
        "project_members",
    ):
        if _has_table(table):
            op.drop_table(table)
