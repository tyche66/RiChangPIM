from __future__ import annotations

import re

from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError

SOURCE_REF_RE = re.compile(r"chunk:[0-9a-fA-F-]{36}")


class CitationValidator:
    def validate_sources(self, sources: list[dict]) -> None:
        for source in sources:
            source_id = str(source.get("source_id") or "")
            if not source_id.startswith("chunk:") and not source_id.startswith("db_"):
                raise KnowledgeGatewayError(
                    KnowledgeErrorCode.CITATION_INVALID,
                    "source_id 非法",
                    status_code=500,
                )

    def validate_answer(self, answer: str, sources: list[dict]) -> None:
        allowed = {str(source.get("source_id")) for source in sources}
        for source_id in SOURCE_REF_RE.findall(answer or ""):
            if source_id not in allowed:
                raise KnowledgeGatewayError(
                    KnowledgeErrorCode.CITATION_INVALID,
                    "回答引用了未授权来源",
                    status_code=500,
                )
