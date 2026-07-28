from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.knowledge.jobs.dispatcher import KnowledgeJobDispatcher
from app.knowledge.jobs.worker import KnowledgeWorker


async def run_dispatcher_once() -> int:
    async with AsyncSessionLocal() as db:
        dispatcher = KnowledgeJobDispatcher(db)
        count = await dispatcher.dispatch_pending_jobs()
        await db.commit()
        return count


async def run_worker_once(*, worker_id: str | None = None) -> bool:
    async with AsyncSessionLocal() as db:
        worker = KnowledgeWorker(db, worker_id=worker_id)
        processed = await worker.process_next_job()
        await db.commit()
        return processed


async def run_worker_forever(
    *,
    worker_id: str | None = None,
    poll_interval: float | None = None,
) -> None:
    interval = poll_interval or settings.KNOWLEDGE_JOB_POLL_INTERVAL_SECONDS
    while True:
        processed = await run_worker_once(worker_id=worker_id)
        if not processed:
            await asyncio.sleep(interval)
