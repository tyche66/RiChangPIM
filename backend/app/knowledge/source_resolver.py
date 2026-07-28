from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError
from app.knowledge.schemas import Source
from app.knowledge.source_access import can_access_document
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.product import Product


class SourceResolver:
    def __init__(self, db):
        self.db = db

    async def resolve(self, source_id: str, current_user: dict) -> Source:
        kind, _, raw_id = source_id.partition(":")
        if source_id.startswith("db_product_"):
            product_id = source_id.removeprefix("db_product_")
            result = await self.db.execute(select(Product).where(Product.id == product_id))
            product = result.scalar_one_or_none()
            if product is None:
                raise KnowledgeGatewayError(
                    KnowledgeErrorCode.CITATION_INVALID,
                    "source 不存在",
                    status_code=404,
                )
            return Source(
                source_id=source_id,
                source_type="database_fact",
                title=f"产品当前事实: {product.product_no}",
                product_id=str(product.id),
                observed_at=datetime.now(UTC),
                access_policy="role_projected",
                open_url=f"/api/v1/knowledge/sources/{source_id}",
            )
        if kind != "chunk" or not raw_id:
            raise KnowledgeGatewayError(
                KnowledgeErrorCode.CITATION_INVALID,
                "未知 source_id",
                status_code=404,
            )
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeChunk.id == raw_id)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        if row is None:
            raise KnowledgeGatewayError(
                KnowledgeErrorCode.CITATION_INVALID,
                "source 不存在",
                status_code=404,
            )
        chunk, document = row
        if not can_access_document(document, current_user):
            raise KnowledgeGatewayError(
                KnowledgeErrorCode.AUTH_DENIED,
                "无权限访问该来源",
                status_code=403,
            )
        return Source(
            source_id=source_id,
            source_type="document",
            title=document.title,
            product_id=str(chunk.product_id) if chunk.product_id else None,
            document_id=str(document.id),
            chunk_id=str(chunk.id),
            page=chunk.page_from,
            section=chunk.section_path,
            quote=chunk.chunk_text[:500] if chunk.chunk_text else None,
            access_policy=document.visibility,
            open_url=f"/api/v1/knowledge/sources/{source_id}",
        )
