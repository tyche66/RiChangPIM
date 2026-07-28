from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.exceptions import AIAdapterUnavailableError
from app.knowledge.jobs.worker import KnowledgeWorker


class _PipelineOk:
    def __init__(self, db):
        self.db = db

    async def upsert_source(self, source_type, source_id):
        return {"source_type": source_type, "source_id": source_id}

    async def delete_source(self, source_type, source_id):
        return 1


class _PipelineUnavailable:
    def __init__(self, db):
        self.db = db

    async def upsert_source(self, source_type, source_id):
        raise AIAdapterUnavailableError("ADAPTER_UNAVAILABLE")


class _PipelineBoom:
    def __init__(self, db):
        self.db = db

    async def upsert_source(self, source_type, source_id):
        raise ValueError("source not found")


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db


def _job(**overrides):
    base = {
        "source_type": "product_card",
        "source_id": "p1",
        "operation": "upsert",
        "status": "pending",
        "attempt_count": 0,
        "max_attempts": 3,
        "completed_at": None,
        "heartbeat_at": None,
        "started_at": None,
        "locked_by": None,
        "locked_at": None,
        "next_attempt_at": None,
        "error_code": None,
        "error_message": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.anyio
async def test_worker_marks_success(mock_db):
    worker = KnowledgeWorker(mock_db, worker_id="w1", pipeline_factory=_PipelineOk)
    job = _job()
    await worker.process_job(job)

    assert job.status == "succeeded"
    assert job.locked_by is None
    assert job.error_code is None
    mock_db.flush.assert_awaited()


@pytest.mark.anyio
async def test_worker_marks_failed_when_ai_unavailable(mock_db):
    worker = KnowledgeWorker(mock_db, worker_id="w1", pipeline_factory=_PipelineUnavailable)
    job = _job()
    await worker.process_job(job)

    assert job.status == "failed"
    assert job.attempt_count == 1
    assert job.error_code == "ADAPTER_UNAVAILABLE"
    assert job.completed_at is None


@pytest.mark.anyio
async def test_worker_marks_dead_after_max_attempts(mock_db):
    worker = KnowledgeWorker(mock_db, worker_id="w1", pipeline_factory=_PipelineBoom)
    job = _job(attempt_count=2, max_attempts=3)
    await worker.process_job(job)

    assert job.status == "dead"
    assert job.attempt_count == 3
    assert job.error_code == "SOURCE_NOT_FOUND"
    assert job.completed_at is not None
