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
        result = await self.db.execute(
            select(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.source_type == source_type,
                KnowledgeIndexJob.source_id == source_id,
                KnowledgeIndexJob.operation == operation,
                KnowledgeIndexJob.status.in_(("pending", "dispatched", "processing", "failed")),
                KnowledgeIndexJob.is_deleted.is_(False),
            )
            .order_by(KnowledgeIndexJob.create_time.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
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
