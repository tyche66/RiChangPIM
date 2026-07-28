from __future__ import annotations

from sqlalchemy import Float, select

from app.adapters.none import NoneAdapter
from app.core.config import settings
from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError
from app.knowledge.indexing.embedding_cache import embed_one_cached
from app.knowledge.retrieval.filters import apply_document_filters
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


async def vector_search(
    db,
    *,
    adapter,
    query: str,
    product_id: str | None,
    current_user: dict,
    limit: int = 10,
):
    if isinstance(adapter, NoneAdapter):
        return []
    try:
        vec = await embed_one_cached(
            adapter,
            query,
            model_name=settings.AI_EMBEDDING_MODEL,
            model_version=settings.AI_EMBEDDING_VERSION or settings.AI_EMBEDDING_MODEL,
        )
    except Exception as exc:  # noqa: BLE001
        raise KnowledgeGatewayError(
            KnowledgeErrorCode.RETRIEVAL_FAILED,
            "向量检索暂不可用，已降级为精确和关键词召回",
            status_code=503,
            retryable=True,
        ) from exc
    if not vec:
        return []

    distance = KnowledgeChunk.embedding.op("<=>", return_type=Float)(vec).label("distance")
    stmt = select(
        KnowledgeChunk.id.label("chunk_id"),
        KnowledgeChunk.document_id.label("document_id"),
        KnowledgeChunk.product_id.label("product_id"),
        KnowledgeChunk.chunk_index.label("chunk_index"),
        KnowledgeChunk.section_path.label("section"),
        KnowledgeChunk.page_from.label("page"),
        KnowledgeChunk.chunk_text.label("quote"),
        KnowledgeDocument.title.label("title"),
        distance,
    ).join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
    stmt = apply_document_filters(stmt, current_user)
    stmt = stmt.where(KnowledgeChunk.embedding.is_not(None))
    if product_id:
        stmt = stmt.where(KnowledgeChunk.product_id == product_id)
    stmt = stmt.order_by(distance.asc()).limit(limit)
    result = await db.execute(stmt)
    rows = []
    for row in result.all():
        payload = dict(row._mapping)
        payload["score"] = round(1.0 - float(payload.pop("distance") or 0.0), 4)
        rows.append(payload)
    return rows
