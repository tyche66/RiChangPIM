from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.adapters.exceptions import AIAdapterError, AIAdapterUnavailableError
from app.core.config import settings
from app.knowledge.indexing.pipeline import KnowledgeIndexingPipeline
from app.knowledge.indexing.status import KnowledgeIndexErrorCode
from app.models.knowledge import KnowledgeIndexJob
from app.observability import metrics as obs_metrics


def sanitize_error_message(exc: Exception) -> str:
    return str(exc).splitlines()[0][:240]


class KnowledgeWorker:
    def __init__(
        self,
        db,
        *,
        worker_id: str | None = None,
        pipeline_factory=KnowledgeIndexingPipeline,
    ):
        self.db = db
        self.worker_id = worker_id or f"worker-{uuid4().hex[:12]}"
        self.pipeline_factory = pipeline_factory

    async def process_next_job(self) -> bool:
        job = await self.claim_next_job()
        if job is None:
            return False
        await self.process_job(job)
        return True

    async def claim_next_job(self) -> KnowledgeIndexJob | None:
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.is_deleted.is_(False),
                KnowledgeIndexJob.status.in_(("pending", "dispatched", "failed")),
                (KnowledgeIndexJob.next_attempt_at.is_(None))
                | (KnowledgeIndexJob.next_attempt_at <= now),
            )
            .order_by(KnowledgeIndexJob.priority.asc(), KnowledgeIndexJob.create_time.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None

        job.status = "processing"
        job.locked_by = self.worker_id
        job.locked_at = now
        job.heartbeat_at = now
        job.started_at = job.started_at or now
        await self.db.flush()
        return job

    async def process_job(self, job: KnowledgeIndexJob) -> None:
        started = datetime.now(UTC)
        pipeline = self.pipeline_factory(self.db)
        try:
            if job.operation in ("upsert", "reindex"):
                await pipeline.upsert_source(job.source_type, job.source_id)
            elif job.operation == "delete":
                await pipeline.delete_source(job.source_type, job.source_id)
            else:
                raise ValueError(f"unsupported operation: {job.operation}")
            await self._mark_succeeded(job)
            obs_metrics.observe_knowledge_job(
                job.operation,
                job.status,
                (datetime.now(UTC) - started).total_seconds(),
            )
        except AIAdapterUnavailableError as exc:
            await self._mark_failed(
                job,
                error_code=KnowledgeIndexErrorCode.ADAPTER_UNAVAILABLE.value,
                error_message=sanitize_error_message(exc),
            )
            obs_metrics.observe_knowledge_job(
                job.operation,
                job.status,
                (datetime.now(UTC) - started).total_seconds(),
            )
        except AIAdapterError as exc:
            await self._mark_failed(
                job,
                error_code=KnowledgeIndexErrorCode.INDEX_UPSERT_FAILED.value,
                error_message=sanitize_error_message(exc),
            )
            obs_metrics.observe_knowledge_job(
                job.operation,
                job.status,
                (datetime.now(UTC) - started).total_seconds(),
            )
        except ValueError as exc:
            code = KnowledgeIndexErrorCode.SOURCE_EMPTY.value
            if "not found" in str(exc):
                code = KnowledgeIndexErrorCode.SOURCE_NOT_FOUND.value
            await self._mark_failed(job, error_code=code, error_message=sanitize_error_message(exc))
            obs_metrics.observe_knowledge_job(
                job.operation,
                job.status,
                (datetime.now(UTC) - started).total_seconds(),
            )
        except Exception as exc:
            code = (
                KnowledgeIndexErrorCode.INDEX_DELETE_FAILED.value
                if job.operation == "delete"
                else KnowledgeIndexErrorCode.INDEX_UPSERT_FAILED.value
            )
            await self._mark_failed(job, error_code=code, error_message=sanitize_error_message(exc))
            obs_metrics.observe_knowledge_job(
                job.operation,
                job.status,
                (datetime.now(UTC) - started).total_seconds(),
            )

    async def _mark_succeeded(self, job: KnowledgeIndexJob) -> None:
        now = datetime.now(UTC)
        job.status = "succeeded"
        job.completed_at = now
        job.heartbeat_at = now
        job.next_attempt_at = None
        job.locked_by = None
        job.locked_at = None
        job.error_code = None
        job.error_message = None
        await self.db.flush()

    async def _mark_failed(
        self,
        job: KnowledgeIndexJob,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        now = datetime.now(UTC)
        job.attempt_count += 1
        job.error_code = error_code
        job.error_message = error_message
        job.heartbeat_at = now
        if job.attempt_count >= job.max_attempts:
            job.status = "dead"
            job.completed_at = now
        else:
            job.status = "failed"
            job.next_attempt_at = now + timedelta(
                seconds=settings.KNOWLEDGE_JOB_RETRY_DELAY_SECONDS
            )
        job.locked_by = None
        job.locked_at = None
        await self.db.flush()
