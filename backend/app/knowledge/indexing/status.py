from __future__ import annotations

from enum import StrEnum


class KnowledgeIndexOutcome(StrEnum):
    INDEXED = "indexed"
    DEGRADED = "degraded"
    FAILED = "failed"


class KnowledgeIndexErrorCode(StrEnum):
    ADAPTER_UNAVAILABLE = "ADAPTER_UNAVAILABLE"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SOURCE_EMPTY = "SOURCE_EMPTY"
    INDEX_DELETE_FAILED = "INDEX_DELETE_FAILED"
    INDEX_UPSERT_FAILED = "INDEX_UPSERT_FAILED"
