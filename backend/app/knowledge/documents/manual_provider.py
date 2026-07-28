from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.knowledge.documents.base import (
    KnowledgeChunkPayload,
    KnowledgeDocumentPayload,
    KnowledgeDocumentProvider,
    stable_content_hash,
)
from app.models.doc_chunk import ProductManualChunk
from app.models.product import ProductManual


class ProductManualKnowledgeProvider(KnowledgeDocumentProvider):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def build(self, source_id: UUID) -> KnowledgeDocumentPayload:
        result = await self.db.execute(
            select(ProductManual)
            .options(selectinload(ProductManual.attachment), selectinload(ProductManual.product))
            .where(ProductManual.id == source_id, ProductManual.is_deleted.is_(False))
        )
        manual = result.scalar_one_or_none()
        if manual is None:
            raise ValueError(f"ProductManual {source_id} not found")

        chunk_rows = await self.db.execute(
            select(ProductManualChunk)
            .where(
                ProductManualChunk.product_manual_id == manual.id,
                ProductManualChunk.is_deleted.is_(False),
            )
            .order_by(ProductManualChunk.chunk_index.asc())
        )
        chunks = [
            KnowledgeChunkPayload(
                chunk_index=row.chunk_index,
                chunk_text=row.chunk_text,
                chunk_type="manual_chunk",
                section_path=f"chunk/{row.chunk_index}",
                token_count=row.chunk_tokens,
                metadata={
                    "legacy_manual_chunk_id": str(row.id),
                    "legacy_product_manual_id": str(row.product_manual_id),
                },
                content_hash=row.chunk_hash,
            )
            for row in chunk_rows.scalars().all()
        ]

        if not chunks:
            parsed_content = (manual.parsed_content or "").strip()
            if not parsed_content:
                raise ValueError(f"ProductManual {source_id} has no parsed content to backfill")
            chunks = [
                KnowledgeChunkPayload(
                    chunk_index=0,
                    chunk_text=parsed_content,
                    chunk_type="manual_fulltext",
                    section_path="manual",
                    token_count=len(parsed_content),
                    metadata={"backfill_mode": "parsed_content"},
                )
            ]

        attachment_name = manual.attachment.file_name if manual.attachment else None
        title = attachment_name or f"产品资料 {manual.id}"
        content_hash = manual.content_hash or stable_content_hash(
            {
                "source_type": "product_manual",
                "source_id": str(manual.id),
                "chunks": [chunk.finalized().content_hash for chunk in chunks],
                "parsed_content": manual.parsed_content or None,
            }
        )

        return KnowledgeDocumentPayload(
            source_type="product_manual",
            source_id=manual.id,
            product_id=manual.product_id,
            attachment_id=manual.attachment_id,
            brand_id=getattr(manual.product, "brand_id", None),
            category_id=getattr(manual.product, "category_id", None),
            title=title,
            doc_type=manual.doc_type,
            content_hash=content_hash,
            parse_status=manual.parse_status,
            index_status="indexed",
            metadata={
                "legacy_product_manual_id": str(manual.id),
                "legacy_index_status": manual.index_status,
                "legacy_parse_status": manual.parse_status,
                "page_count": manual.page_count,
            },
            parser_name=manual.parser_name,
            parser_version=manual.parser_version,
            last_indexed_at=manual.last_indexed_at,
            chunks=chunks,
        )
