from __future__ import annotations

from enum import StrEnum


class KnowledgeJobStatus(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


class KnowledgeJobOperation(StrEnum):
    UPSERT = "upsert"
    DELETE = "delete"
    REINDEX = "reindex"
