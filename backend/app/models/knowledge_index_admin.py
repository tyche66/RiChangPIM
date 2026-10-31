"""夜间向量索引调度服务的持久化模型（v1.9.9）。

三张表：
- ``knowledge_index_setting``        单例配置（启停/调度窗口/批次与退避参数）
- ``knowledge_index_scheduler_state`` 单例运行态（心跳/下次调度/当前运行）
- ``knowledge_index_run``            每次运行（夜间窗口 / run-now）的报告

安全约定：这三张表都不保存任何密钥；embedding 密钥仍只存在于
``ai_provider_config`` / 环境变量，运行报告里的 error_summary 在写入前
统一脱敏（见 services/knowledge_index_scheduler.sanitize_text）。
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.models.base import CommonBase

# 单例行固定主键（与业务数据隔离的保留段），保证幂等 seed。
SETTING_SINGLETON_ID = "00000000-0000-0000-0000-000000000037"
STATE_SINGLETON_ID = "00000000-0000-0000-0000-000000000038"

# run-now 每次最多处理的不同产品数。这是后端硬上限：配置字段只读，
# API 更新会忽略该字段，前端展示也以这里为准。
RUN_NOW_HARD_CAP = 200


class KnowledgeIndexSetting(CommonBase):
    """夜间向量索引配置（单例行）。

    调度窗口按 ``timezone`` 的本地时间解释：``window_start``-``window_end``
    之间处理队列；距 ``window_end`` 不足 ``safety_cutoff_minutes`` 分钟时
    不再发起新的 embedding 请求（给当前批次留收尾时间），窗口结束时
    未完成的任务留在队列里等下一夜。
    """

    __tablename__ = "knowledge_index_setting"

    # 总开关；关闭后不再发起新任务（含 run-now）
    enabled = Column(Boolean, nullable=False, default=True)
    # IANA 时区名
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    # 窗口开始 HH:MM（本地时区）
    window_start = Column(String(5), nullable=False, default="01:00")
    # 窗口结束 HH:MM（本地时区）
    window_end = Column(String(5), nullable=False, default="02:30")
    # 结束前 N 分钟停止新 embedding 请求（02:30 结束 + 5 => 02:25 截止）
    safety_cutoff_minutes = Column(Integer, nullable=False, default=5)
    # 窗口开始时有界 reconcile 的产品数上限
    reconcile_batch_size = Column(Integer, nullable=False, default=200)
    # 单次 embedding 请求合并的产品卡数
    embedding_batch_size = Column(Integer, nullable=False, default=48)
    # 两次 embedding 请求之间的最小间隔秒
    request_interval_seconds = Column(Integer, nullable=False, default=2)
    # 单次 embedding 请求超时秒
    request_timeout_seconds = Column(Integer, nullable=False, default=120)
    # 单个任务最大尝试次数
    max_attempts = Column(Integer, nullable=False, default=3)
    # 指数退避基数秒
    backoff_base_seconds = Column(Integer, nullable=False, default=60)
    # 指数退避上限秒
    backoff_max_seconds = Column(Integer, nullable=False, default=1800)
    # dead 任务保留天数，过期分批清理
    dead_retention_days = Column(Integer, nullable=False, default=90)
    # processing 心跳超过 N 分钟视为僵死并回收
    stale_lock_minutes = Column(Integer, nullable=False, default=15)
    # run-now 单次产品数上限（只读硬上限，受 RUN_NOW_HARD_CAP 校验）
    run_now_max_products = Column(Integer, nullable=False, default=RUN_NOW_HARD_CAP)
    # run-now 最长执行秒
    run_now_max_duration_seconds = Column(Integer, nullable=False, default=600)

    __table_args__ = (
        CheckConstraint("safety_cutoff_minutes BETWEEN 0 AND 30", name="check_ki_setting_cutoff"),
        CheckConstraint(
            "reconcile_batch_size BETWEEN 1 AND 1000", name="check_ki_setting_reconcile"
        ),
        CheckConstraint("embedding_batch_size BETWEEN 1 AND 96", name="check_ki_setting_emb_batch"),
        CheckConstraint(
            "request_interval_seconds BETWEEN 0 AND 300", name="check_ki_setting_interval"
        ),
        CheckConstraint(
            "request_timeout_seconds BETWEEN 10 AND 600", name="check_ki_setting_timeout"
        ),
        CheckConstraint("max_attempts BETWEEN 1 AND 10", name="check_ki_setting_attempts"),
        CheckConstraint(
            "backoff_base_seconds BETWEEN 5 AND 3600", name="check_ki_setting_backoff_base"
        ),
        CheckConstraint(
            "backoff_max_seconds BETWEEN 30 AND 21600", name="check_ki_setting_backoff_max"
        ),
        CheckConstraint(
            "dead_retention_days BETWEEN 7 AND 3650", name="check_ki_setting_dead_retention"
        ),
        CheckConstraint("stale_lock_minutes BETWEEN 5 AND 240", name="check_ki_setting_stale_lock"),
        CheckConstraint(
            f"run_now_max_products = {RUN_NOW_HARD_CAP}",
            name="check_ki_setting_run_now_cap",
        ),
        CheckConstraint(
            "run_now_max_duration_seconds BETWEEN 60 AND 3600",
            name="check_ki_setting_run_now_duration",
        ),
    )


class KnowledgeIndexSchedulerState(CommonBase):
    """调度器运行态（单例行）。

    心跳由每个后台进程按 tick 刷新（多 uvicorn worker 下任一存活即可证明
    服务活着），状态流转只在持有单例锁的进程里发生，避免容器 Up 但调度
    已死的假健康。
    """

    __tablename__ = "knowledge_index_scheduler_state"

    # idle|window_active|run_now_active|stopping|disabled
    scheduler_status = Column(String(20), nullable=False, default="idle")
    # 当前持锁进程标识
    holder = Column(String(128), nullable=True)
    # 最近一次 tick 心跳
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    # 下次窗口开始（UTC）
    next_window_start_at = Column(DateTime(timezone=True), nullable=True)
    # 下次安全截止（UTC）
    next_cutoff_at = Column(DateTime(timezone=True), nullable=True)
    # 进行中的运行报告 id
    current_run_id = Column(PGUUID(as_uuid=True), nullable=True)
    # 最近一次完成的运行报告 id
    last_run_id = Column(PGUUID(as_uuid=True), nullable=True)
    # 最近一次完成时间
    last_run_finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "scheduler_status IN ('idle','window_active','run_now_active','stopping','disabled')",
            name="check_ki_state_status",
        ),
    )


class KnowledgeIndexRun(CommonBase):
    """一次索引运行（夜间窗口或管理员 run-now）的报告。

    token 用量：上游 embeddings 响应带 usage 时记 ``token_usage_actual``；
    否则在 ``token_usage_estimated`` 记按字符估算值（约 4 字符/token），
    两者互斥、绝不把估算值冒充实测。
    """

    __tablename__ = "knowledge_index_run"

    # scheduled|run_now
    trigger_type = Column(String(16), nullable=False)
    # 触发者（调度器为 system）
    operator = Column(String(128), nullable=True)
    operator_id = Column(PGUUID(as_uuid=True), nullable=True)
    # running|completed|stopped|failed
    status = Column(String(16), nullable=False, default="running")
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    timezone_name = Column(String(64), nullable=True)
    # 本次窗口开始（UTC）
    window_start_at = Column(DateTime(timezone=True), nullable=True)
    # 本次窗口结束（UTC）
    window_end_at = Column(DateTime(timezone=True), nullable=True)
    # 本次安全截止（UTC）
    cutoff_at = Column(DateTime(timezone=True), nullable=True)

    # reconcile 扫描到的待索引产品数
    scanned_count = Column(Integer, nullable=False, default=0)
    # 本次新入队任务数
    queued_count = Column(Integer, nullable=False, default=0)
    # 实际调用 embedding 并成功的任务数
    embedding_success_count = Column(Integer, nullable=False, default=0)
    # 内容 hash/模型/版本全匹配而跳过 API 的任务数
    hash_skipped_count = Column(Integer, nullable=False, default=0)
    # 终态失败（dead）任务数
    failed_count = Column(Integer, nullable=False, default=0)
    # 确定性错误隔离（dead）任务数
    quarantined_count = Column(Integer, nullable=False, default=0)
    # 处理的下线任务数
    delete_processed_count = Column(Integer, nullable=False, default=0)
    # 其他来源（如说明书）成功任务数
    other_processed_count = Column(Integer, nullable=False, default=0)
    # embedding 请求批次数
    batch_count = Column(Integer, nullable=False, default=0)
    # 429 限流事件累计影响任务数
    rate_limited_count = Column(Integer, nullable=False, default=0)
    # 僵死锁回收任务数
    stale_reclaimed_count = Column(Integer, nullable=False, default=0)
    # 本次清理的过期 dead 记录数
    dead_purged_count = Column(Integer, nullable=False, default=0)
    # 开始时可执行积压
    backlog_before = Column(Integer, nullable=False, default=0)
    # 结束时剩余可执行积压
    backlog_after = Column(Integer, nullable=False, default=0)

    embedding_model = Column(String(128), nullable=True)
    embedding_version = Column(String(64), nullable=True)
    # 上游实测 token 用量
    token_usage_actual = Column(BigInteger, nullable=True)
    # 上游未回报用量时的估算值
    token_usage_estimated = Column(BigInteger, nullable=True)
    # 脱敏后的错误摘要
    error_summary = Column(Text, nullable=True)
    # 批次数/停止原因等补充信息
    details = Column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint("trigger_type IN ('scheduled','run_now')", name="check_ki_run_trigger"),
        CheckConstraint(
            "status IN ('running','completed','stopped','failed')", name="check_ki_run_status"
        ),
        Index("idx_knowledge_index_run_started", "started_at"),
        Index("idx_knowledge_index_run_trigger_status", "trigger_type", "status"),
    )
