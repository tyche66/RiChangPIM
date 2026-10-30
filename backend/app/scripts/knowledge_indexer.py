"""Continuously reconcile and process product knowledge-card index jobs."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, exists, or_, select, text, update
from sqlalchemy.exc import DataError, IntegrityError, ProgrammingError
from sqlalchemy.orm import aliased

from app.adapters.exceptions import AIAdapterError, AIAdapterRateLimitError
from app.adapters.factory import get_ai_adapter
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.knowledge.documents.base import KnowledgeDocumentPayload, KnowledgeDocumentUpserter
from app.knowledge.documents.product_card import DatabaseProductFactProvider
from app.knowledge.jobs.dispatcher import KnowledgeJobDispatcher
from app.knowledge.jobs.runner import run_worker_once
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeIndexJob
from app.models.product import Brand, Category, Product, ProductTag, Tag

logger = logging.getLogger("knowledge_indexer")

DETERMINISTIC_DB_ERRORS = (IntegrityError, DataError, ProgrammingError)
DETERMINISTIC_ERROR_CODE = "INDEX_DETERMINISTIC_ERROR"


class DeterministicIndexError(RuntimeError):
    """A database/schema error that retrying the same payload cannot fix."""


def _active_job_exists(source_id, operation: str):
    job = aliased(KnowledgeIndexJob)
    return exists(
        select(1).select_from(job).where(
            job.source_type == "product_card",
            job.source_id == source_id,
            job.operation == operation,
            job.status.in_(
                ("pending", "dispatched", "processing", "failed")
            ),
            job.is_deleted.is_(False),
        )
    )


def _deterministic_failure_exists(source_id):
    """Products whose last failure was a deterministic DB error stay quarantined.

    Re-enqueueing them only re-bills the embedding call and fails again, so they
    need an explicit manual reset after the underlying defect is fixed.
    """
    job = aliased(KnowledgeIndexJob)
    return exists(
        select(1).select_from(job).where(
            job.source_type == "product_card",
            job.source_id == source_id,
            job.operation == "upsert",
            job.status == "dead",
            job.error_code == DETERMINISTIC_ERROR_CODE,
            job.is_deleted.is_(False),
        )
    )


def _product_card_needs_indexing():
    """Return products whose current product card is absent or not searchable."""
    document = aliased(KnowledgeDocument)
    chunk = aliased(KnowledgeChunk)
    product_tag = aliased(ProductTag)
    tag = aliased(Tag)
    brand = aliased(Brand)
    category = aliased(Category)
    last_indexed = document.last_indexed_at

    tag_changed = exists(
        select(1)
        .select_from(product_tag)
        .join(tag, tag.id == product_tag.tag_id, isouter=True)
        .where(
            product_tag.product_id == Product.id,
            product_tag.is_deleted.is_(False),
            or_(
                last_indexed.is_(None),
                product_tag.update_time > last_indexed,
                tag.update_time > last_indexed,
            ),
        )
    )
    brand_changed = exists(
        select(1)
        .select_from(brand)
        .where(
            brand.id == Product.brand_id,
            or_(last_indexed.is_(None), brand.update_time > last_indexed),
        )
    )
    category_changed = exists(
        select(1)
        .select_from(category)
        .where(
            category.id == Product.category_id,
            or_(last_indexed.is_(None), category.update_time > last_indexed),
        )
    )

    return (
        select(Product.id)
        .select_from(Product)
        .outerjoin(
            document,
            and_(
                document.source_type == "product_card",
                document.source_id == Product.id,
                document.is_deleted.is_(False),
            ),
        )
        .outerjoin(
            chunk,
            and_(chunk.document_id == document.id, chunk.is_deleted.is_(False)),
        )
        .where(
            Product.is_deleted.is_(False),
            ~_active_job_exists(Product.id, "upsert"),
            ~_deterministic_failure_exists(Product.id),
            or_(
                document.id.is_(None),
                document.index_status != "indexed",
                document.last_indexed_at.is_(None),
                chunk.id.is_(None),
                chunk.embedding.is_(None),
                chunk.embedding_model.is_(None),
                chunk.embedding_model != settings.AI_EMBEDDING_MODEL,
                Product.vector.is_(None),
                Product.update_time > document.last_indexed_at,
                tag_changed,
                brand_changed,
                category_changed,
            ),
        )
        .group_by(Product.id, Product.update_time)
        .order_by(Product.update_time.asc())
    )


def _orphan_product_card_documents():
    """Return active product-card documents whose product was removed."""
    document = aliased(KnowledgeDocument)
    return (
        select(document.source_id)
        .select_from(document)
        .where(
            document.source_type == "product_card",
            document.source_id.is_not(None),
            document.is_deleted.is_(False),
            document.is_active.is_(True),
            ~exists(
                select(1).where(
                    Product.id == document.product_id,
                    Product.is_deleted.is_(False),
                )
            ),
            ~_active_job_exists(document.source_id, "delete"),
        )
    )


async def _sync_existing_product_vectors(db) -> int:
    """Copy already-built card vectors into the legacy product vector column."""
    result = await db.execute(
        text(
            """
            UPDATE product AS p
               SET vector = kc.embedding,
                   update_time = p.update_time
              FROM knowledge_document AS kd
              JOIN knowledge_chunk AS kc ON kc.document_id = kd.id
             WHERE p.id = kd.product_id
               AND p.is_deleted = false
               AND p.vector IS NULL
               AND kd.source_type = 'product_card'
               AND kd.is_deleted = false
               AND kd.is_active = true
               AND kd.index_status = 'indexed'
               AND kc.is_deleted = false
               AND kc.embedding IS NOT NULL
            """
        )
    )
    return result.rowcount or 0


def _clear_job_lock(job: KnowledgeIndexJob) -> None:
    job.locked_by = None
    job.locked_at = None
    job.heartbeat_at = datetime.now(UTC)


def _mark_job_succeeded(job: KnowledgeIndexJob) -> None:
    job.status = "succeeded"
    job.completed_at = datetime.now(UTC)
    job.next_attempt_at = None
    job.error_code = None
    job.error_message = None
    _clear_job_lock(job)


def _mark_job_failed(
    job: KnowledgeIndexJob,
    *,
    message: str,
    rate_limited: bool = False,
    backoff_seconds: float = 3600.0,
) -> None:
    now = datetime.now(UTC)
    job.error_code = "INDEX_UPSERT_FAILED"
    job.error_message = str(message)[:240]
    if rate_limited:
        # Provider quota exhaustion is not a product failure. Preserve the
        # retry budget and wait for the provider window before trying again.
        job.status = "failed"
        job.next_attempt_at = now + timedelta(seconds=backoff_seconds)
    else:
        job.attempt_count += 1
        if job.attempt_count >= job.max_attempts:
            job.status = "dead"
            job.completed_at = now
        else:
            job.status = "failed"
            job.next_attempt_at = now + timedelta(
                seconds=settings.KNOWLEDGE_JOB_RETRY_DELAY_SECONDS
            )
    _clear_job_lock(job)


async def _mark_jobs_failed_isolated(
    job_ids: list[UUID],
    *,
    message: str,
    error_code: str = "INDEX_UPSERT_FAILED",
    dead: bool = False,
) -> None:
    """Record failure in a fresh session.

    The session that hit the database error must be rolled back first; it cannot
    persist its own failure state (that is how the job row previously reverted to
    ``failed`` and kept being re-claimed forever).
    """
    if not job_ids:
        return
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as fail_db:
        await fail_db.execute(
            update(KnowledgeIndexJob)
            .where(KnowledgeIndexJob.id.in_(job_ids))
            .values(
                status="dead" if dead else "failed",
                attempt_count=KnowledgeIndexJob.attempt_count + 1,
                error_code=error_code,
                error_message=str(message)[:240],
                locked_by=None,
                locked_at=None,
                heartbeat_at=now,
                next_attempt_at=(
                    None
                    if dead
                    else now
                    + timedelta(seconds=settings.KNOWLEDGE_JOB_RETRY_DELAY_SECONDS)
                ),
                completed_at=now if dead else None,
            )
        )
        await fail_db.commit()


async def process_product_card_batch_once(
    *,
    batch_size: int,
    worker_id: str,
    rate_limit_backoff: float,
) -> bool:
    """Embed up to ``batch_size`` product cards in one provider request."""
    async with AsyncSessionLocal() as db:
        now = datetime.now(UTC)
        result = await db.execute(
            select(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.source_type == "product_card",
                KnowledgeIndexJob.operation == "upsert",
                KnowledgeIndexJob.is_deleted.is_(False),
                KnowledgeIndexJob.status.in_(
                    ("pending", "dispatched", "failed")
                ),
                (KnowledgeIndexJob.next_attempt_at.is_(None))
                | (KnowledgeIndexJob.next_attempt_at <= now),
            )
            .order_by(KnowledgeIndexJob.priority.asc(), KnowledgeIndexJob.create_time.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        jobs = list(result.scalars().all())
        if not jobs:
            return False

        for job in jobs:
            job.status = "processing"
            job.locked_by = worker_id
            job.locked_at = now
            job.heartbeat_at = now
            job.started_at = job.started_at or now
        await db.flush()

        payloads: list[tuple[KnowledgeIndexJob, KnowledgeDocumentPayload]] = []
        for job in jobs:
            try:
                payload = await DatabaseProductFactProvider(db).build_product_card(job.source_id)
            except ValueError as exc:
                job.error_code = "SOURCE_NOT_FOUND" if "not found" in str(exc) else "SOURCE_EMPTY"
                job.error_message = str(exc)[:240]
                job.status = "dead"
                job.completed_at = datetime.now(UTC)
                _clear_job_lock(job)
                continue
            payloads.append((job, payload))

        if not payloads:
            await db.commit()
            return True

        try:
            adapter = get_ai_adapter()
            inputs = [
                payload.chunks[0].finalized().normalized_text or payload.chunks[0].chunk_text
                for _, payload in payloads
            ]
            vectors = await adapter.embed(inputs)
            if len(vectors) != len(payloads):
                raise ValueError(
                    f"embedding count ({len(vectors)}) does not match "
                    f"product cards ({len(payloads)})"
                )

            indexed_at = datetime.now(UTC)
            upserter = KnowledgeDocumentUpserter(db)
            for (job, payload), vector in zip(payloads, vectors, strict=True):
                chunk = payload.chunks[0].finalized()
                chunk.embedding = vector
                chunk.embedding_model = settings.AI_EMBEDDING_MODEL
                chunk.embedding_version = (
                    settings.AI_EMBEDDING_VERSION or settings.AI_EMBEDDING_MODEL
                )
                payload.chunks = [chunk]
                payload.index_status = "indexed"
                payload.last_indexed_at = indexed_at
                await upserter.upsert(payload)
                await db.execute(
                    update(Product)
                    .where(Product.id == payload.product_id, Product.is_deleted.is_(False))
                    .values(vector=vector, update_time=Product.update_time)
                )
                _mark_job_succeeded(job)
        except AIAdapterRateLimitError as exc:
            for job, _ in payloads:
                _mark_job_failed(
                    job,
                    message=str(exc),
                    rate_limited=True,
                    backoff_seconds=rate_limit_backoff,
                )
            logger.warning(
                "embedding provider rate-limited; deferred %s product cards for %.0fs",
                len(payloads),
                rate_limit_backoff,
            )
        except AIAdapterError as exc:
            for job, _ in payloads:
                _mark_job_failed(job, message=str(exc))
            logger.error("batch product-card embedding failed: %s", exc)
        except DETERMINISTIC_DB_ERRORS as exc:
            await db.rollback()
            await _mark_jobs_failed_isolated(
                [job.id for job, _ in payloads],
                message=str(exc),
                error_code=DETERMINISTIC_ERROR_CODE,
                dead=True,
            )
            logger.critical(
                "deterministic database error; marked %s jobs dead and stopped this cycle: %s",
                len(payloads),
                exc,
            )
            raise DeterministicIndexError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - keep the service alive
            await db.rollback()
            await _mark_jobs_failed_isolated(
                [job.id for job, _ in payloads], message=str(exc)
            )
            logger.exception("batch product-card indexing failed")

        await db.commit()
        return True


async def reconcile_once(*, batch_size: int) -> int:
    """Queue a bounded batch of product-card upserts and orphan deletes."""
    async with AsyncSessionLocal() as db:
        synced = await _sync_existing_product_vectors(db)
        result = await db.execute(_product_card_needs_indexing().limit(batch_size))
        product_ids = [row[0] for row in result.all()]
        dispatcher = KnowledgeJobDispatcher(db)
        queued = 0
        for product_id in product_ids:
            await dispatcher.enqueue_job(
                source_type="product_card",
                source_id=product_id,
                operation="upsert",
                pipeline_version="product-card-v2",
                priority=10,
            )
            queued += 1

        if len(product_ids) < batch_size:
            orphan_result = await db.execute(
                _orphan_product_card_documents().limit(batch_size - len(product_ids))
            )
            for (source_id,) in orphan_result.all():
                if source_id is None:
                    continue
                await dispatcher.enqueue_job(
                    source_type="product_card",
                    source_id=UUID(str(source_id)),
                    operation="delete",
                    pipeline_version="product-card-v2",
                    priority=20,
                )
                queued += 1

        await db.commit()
        if synced:
            logger.info("synchronized %s existing product vectors", synced)
        return queued


async def run_forever(
    *,
    interval: float,
    batch_size: int,
    embedding_batch_size: int,
    rate_limit_backoff: float,
    worker_id: str | None,
) -> None:
    loop = asyncio.get_running_loop()
    next_reconcile = 0.0
    while True:
        now = loop.time()
        if now >= next_reconcile:
            try:
                queued = await reconcile_once(batch_size=batch_size)
                if queued:
                    logger.info("reconciled %s knowledge index jobs", queued)
            except Exception:  # noqa: BLE001 - keep retrying after transient failures
                logger.exception("knowledge index reconciliation failed")
            next_reconcile = loop.time() + interval

        try:
            processed = await process_product_card_batch_once(
                batch_size=embedding_batch_size,
                worker_id=worker_id or "compose-knowledge-indexer",
                rate_limit_backoff=rate_limit_backoff,
            )
            if not processed:
                processed = await run_worker_once(worker_id=worker_id)
        except DeterministicIndexError:
            logger.critical(
                "deterministic index error; pausing indexing for 300s instead of re-embedding"
            )
            await asyncio.sleep(300)
            continue
        except Exception:  # noqa: BLE001 - keep retrying after transient failures
            logger.exception("knowledge index worker iteration failed")
            await asyncio.sleep(min(interval, 10.0))
            continue

        if not processed:
            await asyncio.sleep(min(2.0, max(0.1, next_reconcile - loop.time())))


async def drain_once(
    *,
    batch_size: int,
    embedding_batch_size: int,
    rate_limit_backoff: float,
    worker_id: str | None,
) -> None:
    queued = await reconcile_once(batch_size=batch_size)
    logger.info("queued %s knowledge index jobs", queued)
    while True:
        processed = await process_product_card_batch_once(
            batch_size=embedding_batch_size,
            worker_id=worker_id or "knowledge-indexer-once",
            rate_limit_backoff=rate_limit_backoff,
        )
        if not processed and not await run_worker_once(worker_id=worker_id):
            break


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reconcile-interval",
        type=float,
        default=float(os.getenv("KNOWLEDGE_RECONCILE_INTERVAL_SECONDS", "60")),
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--embedding-batch-size", type=int, default=48)
    parser.add_argument("--rate-limit-backoff", type=float, default=3600.0)
    parser.add_argument("--worker-id", default=None)
    parser.add_argument("--once", action="store_true", help="Reconcile once, drain, then exit")
    args = parser.parse_args()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if (
        args.reconcile_interval <= 0
        or args.batch_size <= 0
        or args.embedding_batch_size <= 0
        or args.rate_limit_backoff <= 0
    ):
        parser.error("intervals and batch sizes must be positive")
    if args.once:
        asyncio.run(
            drain_once(
                batch_size=args.batch_size,
                embedding_batch_size=args.embedding_batch_size,
                rate_limit_backoff=args.rate_limit_backoff,
                worker_id=args.worker_id,
            )
        )
    else:
        asyncio.run(
            run_forever(
                interval=args.reconcile_interval,
                batch_size=args.batch_size,
                embedding_batch_size=args.embedding_batch_size,
                rate_limit_backoff=args.rate_limit_backoff,
                worker_id=args.worker_id,
            )
        )


if __name__ == "__main__":
    main()
