from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.models.knowledge import KnowledgeIndexJob


class KnowledgeJobDispatcher:
    def __init__(self, db):
        self.db = db

    async def enqueue_job(
        self,
        *,
        source_type: str,
        source_id: UUID | None,
        operation: str,
        content_hash: str | None = None,
        pipeline_version: str | None = None,
        priority: int = 100,
        max_attempts: int | None = None,
        created_by=None,
        trace_id: str | None = None,
    ) -> KnowledgeIndexJob:
        reusable = await self.db.execute(
            select(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.source_type == source_type,
                KnowledgeIndexJob.source_id == source_id,
                KnowledgeIndexJob.operation == operation,
                KnowledgeIndexJob.status.in_(("pending", "dispatched")),
                KnowledgeIndexJob.is_deleted.is_(False),
            )
            .order_by(KnowledgeIndexJob.create_time.desc())
            .limit(1)
        )
        job = reusable.scalar_one_or_none()
        if job is not None:
            job.status = "pending"
            job.content_hash = content_hash
            job.pipeline_version = pipeline_version
            job.priority = priority
            job.max_attempts = max_attempts or settings.KNOWLEDGE_JOB_MAX_ATTEMPTS
            job.created_by = created_by
            job.trace_id = trace_id
            job.next_attempt_at = None
            job.error_code = None
            job.error_message = None
            job.locked_by = None
            job.locked_at = None
            job.heartbeat_at = None
            await self.db.flush()
            return job

        # processing 中存在任务：飞行中的工作不劫持、不重置；若本次内容变更
        # 未被飞行任务覆盖，reconcile 依赖 update_time 对比在下一轮自愈。
        # （活动任务唯一索引也禁止同一产品同时存在 processing 与新 pending。）
        processing = await self.db.execute(
            select(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.source_type == source_type,
                KnowledgeIndexJob.source_id == source_id,
                KnowledgeIndexJob.operation == operation,
                KnowledgeIndexJob.status == "processing",
                KnowledgeIndexJob.is_deleted.is_(False),
            )
            .order_by(KnowledgeIndexJob.create_time.desc())
            .limit(1)
        )
        in_flight = processing.scalar_one_or_none()
        if in_flight is not None:
            return in_flight

        # 不复用 failed 任务：业务变更（编辑/导入/克隆）入队时，原 failed
        # 任务的指数退避与失败计数必须原样保留（否则每次编辑都把退避
        # 清零，产品反复立即重试重复计费）。这里新建一条 pending 任务；
        # 领取侧按"最新非终态任务"去重，旧 failed 自动让位。
        job = KnowledgeIndexJob(
            source_type=source_type,
            source_id=source_id,
            operation=operation,
        )
        self.db.add(job)

        job.status = "pending"
        job.content_hash = content_hash
        job.pipeline_version = pipeline_version
        job.priority = priority
        job.max_attempts = max_attempts or settings.KNOWLEDGE_JOB_MAX_ATTEMPTS
        job.created_by = created_by
        job.trace_id = trace_id
        job.next_attempt_at = None
        job.error_code = None
        job.error_message = None
        job.locked_by = None
        job.locked_at = None
        job.heartbeat_at = None
        await self.db.flush()
        return job

    async def dispatch_pending_jobs(self, *, batch_size: int | None = None) -> int:
        now = datetime.now(UTC)
        limit = batch_size or settings.KNOWLEDGE_JOB_BATCH_SIZE
        result = await self.db.execute(
            select(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.is_deleted.is_(False),
                KnowledgeIndexJob.status == "pending",
                (KnowledgeIndexJob.next_attempt_at.is_(None))
                | (KnowledgeIndexJob.next_attempt_at <= now),
            )
            .order_by(KnowledgeIndexJob.priority.asc(), KnowledgeIndexJob.create_time.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = result.scalars().all()
        for job in jobs:
            job.status = "dispatched"
        await self.db.flush()
        return len(jobs)


async def enqueue_product_card(
    db, product_id: UUID, *, operation: str = "upsert", created_by=None
) -> None:
    """产品增改删后登记卡片重建/下线任务（与调用方同一事务，由调用方 commit）。"""
    await KnowledgeJobDispatcher(db).enqueue_job(
        source_type="product_card",
        source_id=product_id,
        operation=operation,
        created_by=created_by,
    )


async def enqueue_product_manual(
    db, manual_id: UUID, *, operation: str = "upsert", created_by=None
) -> None:
    """说明书上传/解析/删除后登记建向量任务。"""
    await KnowledgeJobDispatcher(db).enqueue_job(
        source_type="product_manual",
        source_id=manual_id,
        operation=operation,
        created_by=created_by,
    )
