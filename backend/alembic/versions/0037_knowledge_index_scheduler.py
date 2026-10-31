"""夜间向量索引调度服务：设置/运行态/运行报告 + 活动任务唯一索引

新增三张表：
  - knowledge_index_setting         单例配置（启停、调度窗口、批次与退避参数）
  - knowledge_index_scheduler_state 单例运行态（心跳、下次调度、当前运行）
  - knowledge_index_run             运行报告（夜间窗口 / run-now）

数据完整性修复：同一 (source_type, source_id, operation) 允许多条历史任务，
但未终态（pending/dispatched/processing）任务在部分唯一索引约束下全局最多
一条，防止重复 reconcile / 多 worker 对同一产品重复计费 embedding。建索引
前先把同组内较旧的未完成任务软删（保留最新一条，绝不物理删除）。

权限：新增 ``knowledge:index`` 管理权限点并映射给 admin 角色。

Revision ID: 0037_knowledge_index_scheduler
Revises: 0036_product_delivery_period_vision_tags
Create Date: 2026-10-31
"""
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0037_knowledge_index_scheduler"
down_revision: str | None = "0036_product_delivery_period_vision_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTING_ID = "00000000-0000-0000-0000-000000000037"
STATE_ID = "00000000-0000-0000-0000-000000000038"

ACTIVE_JOB_INDEX = "uq_knowledge_index_job_active"
PERM_CODE = "knowledge:index"

def _base_columns() -> list[sa.Column]:
    """每张表独立生成公共列（Column 实例不可跨表复用）。"""
    return [
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
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
            "is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    ]


def _base_table(name: str, *columns: sa.Column) -> sa.Table:
    return sa.Table(
        name,
        sa.MetaData(),
        *_base_columns(),
        *columns,
    )


def upgrade() -> None:
    # 管线标签现在编码 embedding model/version（dead 隔离判断依赖），
    # 32 字符不够；扩到 128（可空元数据列，加宽无损、可回退）。
    op.alter_column(
        "knowledge_index_job",
        "pipeline_version",
        existing_type=sa.String(32),
        type_=sa.String(128),
    )

    setting = _base_table(
        "knowledge_index_setting",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("window_start", sa.String(5), nullable=False, server_default="01:00"),
        sa.Column("window_end", sa.String(5), nullable=False, server_default="02:30"),
        sa.Column("safety_cutoff_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("reconcile_batch_size", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("embedding_batch_size", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("request_interval_seconds", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("request_timeout_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("backoff_base_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("backoff_max_seconds", sa.Integer(), nullable=False, server_default="1800"),
        sa.Column("dead_retention_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("stale_lock_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("run_now_max_products", sa.Integer(), nullable=False, server_default="200"),
        sa.Column(
            "run_now_max_duration_seconds", sa.Integer(), nullable=False, server_default="600"
        ),
        sa.CheckConstraint(
            "safety_cutoff_minutes BETWEEN 0 AND 30", name="check_ki_setting_cutoff"
        ),
        sa.CheckConstraint(
            "reconcile_batch_size BETWEEN 1 AND 1000", name="check_ki_setting_reconcile"
        ),
        sa.CheckConstraint(
            "embedding_batch_size BETWEEN 1 AND 96", name="check_ki_setting_emb_batch"
        ),
        sa.CheckConstraint(
            "request_interval_seconds BETWEEN 0 AND 300", name="check_ki_setting_interval"
        ),
        sa.CheckConstraint(
            "request_timeout_seconds BETWEEN 10 AND 600", name="check_ki_setting_timeout"
        ),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 10", name="check_ki_setting_attempts"),
        sa.CheckConstraint(
            "backoff_base_seconds BETWEEN 5 AND 3600", name="check_ki_setting_backoff_base"
        ),
        sa.CheckConstraint(
            "backoff_max_seconds BETWEEN 30 AND 21600", name="check_ki_setting_backoff_max"
        ),
        sa.CheckConstraint(
            "dead_retention_days BETWEEN 7 AND 3650", name="check_ki_setting_dead_retention"
        ),
        sa.CheckConstraint(
            "stale_lock_minutes BETWEEN 5 AND 240", name="check_ki_setting_stale_lock"
        ),
        sa.CheckConstraint("run_now_max_products = 200", name="check_ki_setting_run_now_cap"),
        sa.CheckConstraint(
            "run_now_max_duration_seconds BETWEEN 60 AND 3600",
            name="check_ki_setting_run_now_duration",
        ),
    )
    op.create_table(
        "knowledge_index_setting",
        *setting.columns,
        *setting.constraints,
    )
    op.execute(
        setting.insert().values(
            id=SETTING_ID,
            create_time=sa.func.now(),
            update_time=sa.func.now(),
            is_deleted=False,
        )
    )

    state = _base_table(
        "knowledge_index_scheduler_state",
        sa.Column("scheduler_status", sa.String(20), nullable=False, server_default="idle"),
        sa.Column("holder", sa.String(128), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_window_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_cutoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_run_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("last_run_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("last_run_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scheduler_status IN ('idle','window_active','run_now_active','stopping','disabled')",
            name="check_ki_state_status",
        ),
    )
    op.create_table(
        "knowledge_index_scheduler_state",
        *state.columns,
        *state.constraints,
    )
    op.execute(
        state.insert().values(
            id=STATE_ID,
            create_time=sa.func.now(),
            update_time=sa.func.now(),
            is_deleted=False,
            scheduler_status="idle",
        )
    )

    run = _base_table(
        "knowledge_index_run",
        sa.Column("trigger_type", sa.String(16), nullable=False),
        sa.Column("operator", sa.String(128), nullable=True),
        sa.Column("operator_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone_name", sa.String(64), nullable=True),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scanned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hash_skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quarantined_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delete_processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("other_processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("batch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rate_limited_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stale_reclaimed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dead_purged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("backlog_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("backlog_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(128), nullable=True),
        sa.Column("embedding_version", sa.String(64), nullable=True),
        sa.Column("token_usage_actual", sa.BigInteger(), nullable=True),
        sa.Column("token_usage_estimated", sa.BigInteger(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.CheckConstraint("trigger_type IN ('scheduled','run_now')", name="check_ki_run_trigger"),
        sa.CheckConstraint(
            "status IN ('running','completed','stopped','failed')",
            name="check_ki_run_status",
        ),
    )
    op.create_table("knowledge_index_run", *run.columns, *run.constraints)
    op.create_index(
        "idx_knowledge_index_run_started",
        "knowledge_index_run",
        ["started_at"],
    )
    op.create_index(
        "idx_knowledge_index_run_trigger_status",
        "knowledge_index_run",
        ["trigger_type", "status"],
    )

    # -- 同组未终态任务去重：只保留每组最新一条，其余软删（保留审计痕迹）。
    op.execute(
        sa.text(
            """
            UPDATE knowledge_index_job older
               SET is_deleted = true,
                   deleted_at = now(),
                   update_time = now()
              FROM knowledge_index_job newer
             WHERE older.source_type = newer.source_type
               AND older.source_id IS NOT DISTINCT FROM newer.source_id
               AND older.operation = newer.operation
               AND older.is_deleted = false
               AND newer.is_deleted = false
               AND older.status IN ('pending', 'dispatched', 'processing')
               AND newer.status IN ('pending', 'dispatched', 'processing')
               AND (older.create_time, older.id) < (newer.create_time, newer.id)
            """
        )
    )
    op.create_index(
        ACTIVE_JOB_INDEX,
        "knowledge_index_job",
        ["source_type", "source_id", "operation"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'dispatched', 'processing') AND is_deleted = false"
        ),
    )

    # -- knowledge_document 活动唯一约束：同键只允许一个未删除文档，防止
    #    并发 upsert 双插后 _get_existing_document 出现 MultipleResultsFound。
    #    先把同键较旧的活动行软删（保留审计痕迹，绝不物理删除）。
    op.execute(
        sa.text(
            """
            UPDATE knowledge_document older
               SET is_deleted = true,
                   deleted_at = now(),
                   update_time = now()
              FROM knowledge_document newer
             WHERE older.source_type = newer.source_type
               AND older.source_id IS NOT DISTINCT FROM newer.source_id
               AND older.is_deleted = false
               AND newer.is_deleted = false
               AND (older.create_time, older.id) < (newer.create_time, newer.id)
            """
        )
    )
    op.create_index(
        "uq_knowledge_document_active",
        "knowledge_document",
        ["source_type", "source_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    # -- 权限点 + admin 角色映射（幂等 seed，模式与 0011 一致）。
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO permission (id, perm_code, perm_name, resource, action, type,
                                    create_time, update_time, is_deleted)
            SELECT :id, :perm_code, :perm_name, :resource, :action, :ptype,
                   now(), now(), false
            WHERE NOT EXISTS (
                SELECT 1 FROM permission
                WHERE perm_code = :perm_code AND is_deleted = false
            )
            """
        ),
        {
            "id": str(uuid4()),
            "perm_code": PERM_CODE,
            "perm_name": "向量索引管理",
            "resource": "knowledge_index",
            "action": "manage",
            "ptype": "write",
        },
    )
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO role_permission (id, role_id, permission_id,
                                         create_time, update_time, is_deleted)
            SELECT :id, r.id, p.id, now(), now(), false
            FROM role r, permission p
            WHERE r.role_code = 'admin'
              AND p.perm_code = :perm_code
              AND r.is_deleted = false
              AND p.is_deleted = false
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id
                    AND rp.permission_id = p.id
                    AND rp.is_deleted = false
              )
            """
        ),
        {"id": str(uuid4()), "perm_code": PERM_CODE},
    )


def downgrade() -> None:
    op.alter_column(
        "knowledge_index_job",
        "pipeline_version",
        existing_type=sa.String(128),
        type_=sa.String(32),
    )
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM role_permission rp
            USING permission p
            WHERE rp.permission_id = p.id
              AND p.perm_code = :perm_code
            """
        ),
        {"perm_code": PERM_CODE},
    )
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM permission
            WHERE perm_code = :perm_code AND is_deleted = false
            """
        ),
        {"perm_code": PERM_CODE},
    )
    op.drop_index(ACTIVE_JOB_INDEX, table_name="knowledge_index_job")
    op.drop_index("uq_knowledge_document_active", table_name="knowledge_document")
    op.drop_index("idx_knowledge_index_run_trigger_status", table_name="knowledge_index_run")
    op.drop_index("idx_knowledge_index_run_started", table_name="knowledge_index_run")
    op.drop_table("knowledge_index_run")
    op.drop_table("knowledge_index_scheduler_state")
    op.drop_table("knowledge_index_setting")
