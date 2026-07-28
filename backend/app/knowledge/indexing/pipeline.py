from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.adapters.exceptions import AIAdapterUnavailableError
from app.adapters.factory import get_ai_adapter
from app.adapters.none import NoneAdapter
from app.core.config import settings
from app.knowledge.documents.base import KnowledgeDocumentPayload, KnowledgeDocumentUpserter
from app.knowledge.documents.manual_provider import ProductManualKnowledgeProvider
from app.knowledge.documents.product_card import DatabaseProductFactProvider
from app.knowledge.indexing.chunker import chunk_text
from app.knowledge.indexing.embedder import embed_chunks
from app.knowledge.indexing.status import KnowledgeIndexErrorCode
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


class KnowledgeIndexingPipeline:
    def __init__(self, db):
        self.db = db
        self.adapter = get_ai_adapter()

    async def upsert_source(self, source_type: str, source_id: UUID | None) -> KnowledgeDocument:
        if source_id is None:
            raise ValueError("source_id is required for upsert/reindex jobs")

        payload = await self._build_payload(source_type, source_id)
        embedded_payload = await self._embed_payload(payload)
        document = await KnowledgeDocumentUpserter(self.db).upsert(embedded_payload)
        document.index_status = "indexed"
        document.last_indexed_at = datetime.now(UTC)
        await self.db.flush()
        return document

    async def delete_source(self, source_type: str, source_id: UUID | None) -> int:
        if source_id is None:
            raise ValueError("source_id is required for delete jobs")
        result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source_type == source_type,
                KnowledgeDocument.source_id == source_id,
                KnowledgeDocument.is_deleted.is_(False),
            )
        )
        document = result.scalar_one_or_none()
        if document is None:
            return 0

        document.is_active = False
        document.update_time = datetime.now(UTC)
        chunk_result = await self.db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
        )
        now = datetime.now(UTC)
        count = 0
        for chunk in chunk_result.scalars().all():
            if not chunk.is_deleted:
                chunk.is_deleted = True
                chunk.deleted_at = now
                count += 1
        await self.db.flush()
        return count

    async def _build_payload(self, source_type: str, source_id: UUID) -> KnowledgeDocumentPayload:
        if source_type == "product_card":
            return await DatabaseProductFactProvider(self.db).build_product_card(source_id)
        if source_type == "product_manual":
            payload = await ProductManualKnowledgeProvider(self.db).build(source_id)
            chunk_metadata = payload.chunks[0].metadata if len(payload.chunks) == 1 else None
            if chunk_metadata and chunk_metadata.get("backfill_mode") == "parsed_content":
                text = payload.chunks[0].chunk_text
                payload.chunks = chunk_text(
                    text,
                    target_tokens=max(300, min(settings.AI_RAG_CHUNK_SIZE, 600)),
                    overlap_tokens=max(20, settings.AI_RAG_CHUNK_OVERLAP // 4),
                )
            return payload
        raise ValueError(f"unsupported source_type: {source_type}")

    async def _embed_payload(self, payload: KnowledgeDocumentPayload) -> KnowledgeDocumentPayload:
        if isinstance(self.adapter, NoneAdapter):
            raise AIAdapterUnavailableError(KnowledgeIndexErrorCode.ADAPTER_UNAVAILABLE.value)
        payload.chunks = await embed_chunks(
            self.adapter,
            [chunk.finalized() for chunk in payload.chunks],
            model_name=settings.AI_EMBEDDING_MODEL,
            model_version=settings.AI_EMBEDDING_VERSION or settings.AI_EMBEDDING_MODEL,
        )
        payload.index_status = "indexed"
        payload.last_indexed_at = datetime.now(UTC)
        return payload
