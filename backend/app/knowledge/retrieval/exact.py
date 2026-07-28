from __future__ import annotations

from sqlalchemy import or_, select

from app.knowledge.retrieval.filters import apply_document_filters
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.product import Product


async def exact_search(db, *, query: str, product_id: str | None, current_user: dict, limit: int = 10):
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
            KnowledgeDocument.source_type.label("document_source_type"),
        )
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .join(Product, Product.id == KnowledgeChunk.product_id, isouter=True)
    )
    stmt = apply_document_filters(stmt, current_user)
    if product_id:
        stmt = stmt.where(KnowledgeChunk.product_id == product_id)
    else:
        stmt = stmt.where(
            or_(
                Product.product_no.ilike(f"%{query}%"),
                KnowledgeDocument.title.ilike(f"%{query}%"),
            )
        )
    stmt = stmt.order_by(KnowledgeDocument.title.asc(), KnowledgeChunk.chunk_index.asc()).limit(limit)
    result = await db.execute(stmt)
    return [dict(row._mapping) for row in result.all()]
