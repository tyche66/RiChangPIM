from __future__ import annotations

from sqlalchemy import func, select

from app.knowledge.retrieval.filters import apply_document_filters
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


async def keyword_search(db, *, query: str, product_id: str | None, current_user: dict, limit: int = 10):
    ts_query = func.plainto_tsquery("simple", query)
    rank = func.ts_rank_cd(KnowledgeChunk.text_search, ts_query).label("rank")
    stmt = (
        select(
            KnowledgeChunk.id.label("chunk_id"),
            KnowledgeChunk.document_id.label("document_id"),
            KnowledgeChunk.product_id.label("product_id"),
            KnowledgeChunk.chunk_index.label("chunk_index"),
            KnowledgeChunk.section_path.label("section"),
            KnowledgeChunk.page_from.label("page"),
            KnowledgeChunk.chunk_text.label("quote"),
            KnowledgeDocument.title.label("title"),
            rank,
        )
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
    )
    stmt = apply_document_filters(stmt, current_user)
    stmt = stmt.where(KnowledgeChunk.text_search.op("@@")(ts_query))
    if product_id:
        stmt = stmt.where(KnowledgeChunk.product_id == product_id)
    stmt = stmt.order_by(rank.desc(), KnowledgeChunk.chunk_index.asc()).limit(limit)
    result = await db.execute(stmt)
    return [dict(row._mapping) for row in result.all()]
