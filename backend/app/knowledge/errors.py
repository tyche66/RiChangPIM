from __future__ import annotations

from enum import StrEnum


class KnowledgeErrorCode(StrEnum):
    AUTH_DENIED = "AUTH_DENIED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    PLAN_INVALID = "PLAN_INVALID"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_FAILED = "TOOL_FAILED"
    RETRIEVAL_EMPTY = "RETRIEVAL_EMPTY"
    RETRIEVAL_FAILED = "RETRIEVAL_FAILED"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_RATE_LIMIT = "MODEL_RATE_LIMIT"
    MODEL_INVALID = "MODEL_INVALID"
    CITATION_INVALID = "CITATION_INVALID"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    CAPABILITY_DISABLED = "CAPABILITY_DISABLED"


class KnowledgeGatewayError(Exception):
    def __init__(
        self,
        code: KnowledgeErrorCode,
        message: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
