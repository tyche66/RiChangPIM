"""crm_detail

CRM-Lite 核心表：customers / projects / project_members / entity_stage_logs /
customer_dialogues / customer_dialogue_attachments / requirements / follow_ups /
project_assets，并补齐 proposal.customer_id / proposal.project_id 的外键约束。

背景（仓库一致性修复）：
  这些表在早期版本由 ``Base.metadata.create_all``（seed_data / init_admin）直接建出，
  但从未有对应的 alembic revision。本迁移把它们纳入受版本管理的链，
  使全新库也能通过 ``alembic upgrade head`` 得到与模型一致的 schema。

设计约束：
  * 所有 DDL 均幂等——表/索引/约束已存在时跳过，避免在"已被 create_all
    建过表"的库上重复执行报错。
  * 全部列先 nullable 或带默认值，旧数据可读。
  * ``downgrade`` 仅删本迁移真正创建的对象。

Revision ID: 0019_crm_detail
Revises: 0018_crm_core
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0019_crm_detail"
down_revision: Union[str, None] = "0018_crm_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_index(table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in _inspector().get_indexes(table))


def _has_fk(table: str, constraint_name: str) -> bool:
    return any(
        fk.get("name") == constraint_name for fk in _inspector().get_foreign_keys(table)
    )


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


def _create_table_if_missing(name: str, *columns, **kw):
    if _has_table(name):
        return
    op.create_table(name, *columns, **kw)


def _create_index_if_missing(
    table: str, index: str, columns: list[str], *, unique: bool = False, where=None
):
    if not _has_table(table) or _has_index(table, index):
        return
    op.create_index(index, table, columns, unique=unique, postgresql_where=where)


def upgrade() -> None:
    # 1) customers
    _create_table_if_missing(
        "customers",
        *_common_columns(),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("customer_no", sa.String(32), nullable=True),
        sa.Column("source", sa.String(32), server_default=sa.text("'other'"), nullable=False),
        sa.Column("level", sa.String(16), nullable=True),
        sa.Column("stage", sa.String(20), server_default=sa.text("'lead'"), nullable=False),
        sa.Column(
            "owner_sales_id", PGUUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("phone_norm", sa.String(32), nullable=True),
        sa.Column("wechat", sa.String(128), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("budget_min", sa.Float(), nullable=True),
        sa.Column("budget_max", sa.Float(), nullable=True),
        sa.Column("style_preference", sa.Text(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint(
            "stage IN ('lead','contacted','needs','quoted','won','lost')", name="ck_customers_stage"
        ),
        sa.CheckConstraint(
            "level IS NULL OR level IN ('A','B','C')", name="ck_customers_level"
        ),
        sa.CheckConstraint(
            "source IN ('new_media','store','referral','exhibition','other')", name="ck_customers_source"
        ),
        sa.CheckConstraint(
            "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max", name="ck_customers_budget"
        ),
    )
    _create_index_if_missing("customers", "ix_customers_owner_stage", ["owner_sales_id", "stage"], where=sa.text("is_deleted = false"))
    _create_index_if_missing("customers", "ix_customers_create_time", ["create_time"], where=sa.text("is_deleted = false"))
    _create_index_if_missing("customers", "ix_customers_phone_norm", ["phone_norm"], where=sa.text("is_deleted = false AND phone_norm IS NOT NULL"))
    _create_index_if_missing("customers", "ix_customers_activity", ["last_activity_at"], where=sa.text("is_deleted = false"))
    _create_index_if_missing("customers", "ix_customers_name", ["name"])
    _create_index_if_missing("customers", "uq_customers_no", ["customer_no"], unique=True, where=sa.text("is_deleted = false AND customer_no IS NOT NULL"))

    # 3) projects
    _create_table_if_missing(
        "projects",
        *_common_columns(),
        sa.Column("customer_id", PGUUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("project_type", sa.String(32), server_default=sa.text("'other'"), nullable=False),
        sa.Column("stage", sa.String(20), server_default=sa.text("'lead'"), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("budget", sa.Float(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint(
            "stage IN ('lead','measuring','design','quoted','producing','delivered','closed','cancelled')",
            name="ck_projects_stage",
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','done','cancelled')", name="ck_projects_status"
        ),
        sa.CheckConstraint(
            "start_date IS NULL OR end_date IS NULL OR start_date <= end_date", name="ck_projects_dates"
        ),
    )
    _create_index_if_missing("projects", "ix_projects_customer", ["customer_id"], where=sa.text("is_deleted = false"))
    _create_index_if_missing("projects", "ix_projects_stage", ["stage", "status"], where=sa.text("is_deleted = false"))
    _create_index_if_missing("projects", "ix_projects_activity", ["last_activity_at"], where=sa.text("is_deleted = false"))
    _create_index_if_missing("projects", "uq_projects_code", ["code"], unique=True, where=sa.text("is_deleted = false AND code IS NOT NULL"))

    # 4) project_members
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

    # 5) entity_stage_logs
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

    # 6) customer_dialogues
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

    # 7) customer_dialogue_attachments
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

    # 8) requirements
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

    # 9) follow_ups
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

    # 10) project_assets
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

    # 11) proposal 外键（模型已声明 ForeignKey，但早期迁移未落地）
    #     放在最后：引用 customers / projects，必须等二者就绪。
    for constraint_name, column, referent_table in (
        ("fk_proposal_customer", "customer_id", "customers"),
        ("fk_proposal_project", "project_id", "projects"),
    ):
        if (
            _has_table("proposal")
            and _has_table(referent_table)
            and not _has_fk("proposal", constraint_name)
        ):
            op.create_foreign_key(
                constraint_name,
                "proposal",
                referent_table,
                [column],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    # 先删 proposal 外键（引用 customers/projects），否则 DROP TABLE 会因依赖失败。
    for constraint_name in ("fk_proposal_project", "fk_proposal_customer"):
        if _has_table("proposal") and _has_fk("proposal", constraint_name):
            op.drop_constraint(constraint_name, "proposal", type_="foreignkey")

    for table in (
        "project_assets",
        "follow_ups",
        "requirements",
        "customer_dialogue_attachments",
        "customer_dialogues",
        "entity_stage_logs",
        "project_members",
        "projects",
        "customers",
    ):
        if _has_table(table):
            op.drop_table(table)
