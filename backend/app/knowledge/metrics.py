from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def record_query(*, trace_id: str, intent: str, status: str, latency_ms: int) -> None:
    logger.info(
        "knowledge_query trace_id=%s intent=%s status=%s latency_ms=%s",
        trace_id,
        intent,
        status,
        latency_ms,
    )


def record_tool(*, trace_id: str, tool: str, status: str, latency_ms: int, result_count: int = 0) -> None:
    logger.info(
        "knowledge_tool trace_id=%s tool=%s status=%s latency_ms=%s result_count=%s",
        trace_id,
        tool,
        status,
        latency_ms,
        result_count,
    )
