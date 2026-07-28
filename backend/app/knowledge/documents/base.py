from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


def stable_content_hash(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_text(text: str | None) -> str:
    return " ".join((text or "").split())


@dataclass(slots=True)
class KnowledgeChunkPayload:
    chunk_index: int
    chunk_text: str
    chunk_type: str = "text"
    section_path: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    token_count: int | None = None
    metadata: dict | None = None
    normalized_text: str | None = None
    embedding: list[float] | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None
    content_hash: str | None = None

    def finalized(self) -> KnowledgeChunkPayload:
        normalized = self.normalized_text or normalize_text(self.chunk_text)
        content_hash = self.content_hash or stable_content_hash(
            {
                "chunk_index": self.chunk_index,
                "chunk_type": self.chunk_type,
                "section_path": self.section_path,
                "page_from": self.page_from,
                "page_to": self.page_to,
                "chunk_text": self.chunk_text,
                "normalized_text": normalized,
                "metadata": self.metadata or {},
            }
        )
        return KnowledgeChunkPayload(
            chunk_index=self.chunk_index,
            chunk_text=self.chunk_text,
            chunk_type=self.chunk_type,
            section_path=self.section_path,
            page_from=self.page_from,
            page_to=self.page_to,
            token_count=self.token_count,
            metadata=self.metadata,
            normalized_text=normalized,
            embedding=self.embedding,
            embedding_model=self.embedding_model,
            embedding_version=self.embedding_version,
            content_hash=content_hash,
        )


@dataclass(slots=True)
class KnowledgeDocumentPayload:
    source_type: str
    source_id: UUID | None
    title: str
    doc_type: str
    content_hash: str
    product_id: UUID | None = None
    category_id: UUID | None = None
    brand_id: UUID | None = None
    attachment_id: UUID | None = None
    version: str | None = None
    language: str | None = None
    parse_status: str = "parsed"
    index_status: str = "indexed"
    is_active: bool = True
    visibility: str = "internal"
    required_permission: str | None = None
    metadata: dict | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    last_indexed_at: datetime | None = None
    effective_at: datetime | None = None
    expired_at: datetime | None = None
    chunks: list[KnowledgeChunkPayload] = field(default_factory=list)


class KnowledgeDocumentProvider(Protocol):
    async def build(self, source_id: UUID) -> KnowledgeDocumentPayload: ...


class ProductFactProvider(Protocol):
    async def build_product_card(self, product_id: UUID) -> KnowledgeDocumentPayload: ...


class KnowledgeDocumentUpserter:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(self, payload: KnowledgeDocumentPayload) -> KnowledgeDocument:
        document = await self._get_existing_document(payload.source_type, payload.source_id)
        now = datetime.now(UTC)

        if document and not document.is_deleted and document.content_hash == payload.content_hash:
            document.is_active = payload.is_active
            document.visibility = payload.visibility
            document.required_permission = payload.required_permission
            document.last_indexed_at = payload.last_indexed_at or now
            await self.db.flush()
            return document

        if document is None:
            document = KnowledgeDocument(
                source_type=payload.source_type,
                source_id=payload.source_id,
            )
            self.db.add(document)

        document.product_id = payload.product_id
        document.category_id = payload.category_id
        document.brand_id = payload.brand_id
        document.attachment_id = payload.attachment_id
        document.title = payload.title
        document.doc_type = payload.doc_type
        document.version = payload.version
        document.language = payload.language
        document.content_hash = payload.content_hash
        document.parse_status = payload.parse_status
        document.index_status = payload.index_status
        document.is_active = payload.is_active
        document.visibility = payload.visibility
        document.required_permission = payload.required_permission
        document.metadata_json = payload.metadata
        document.parser_name = payload.parser_name
        document.parser_version = payload.parser_version
        document.last_indexed_at = payload.last_indexed_at or now
        document.effective_at = payload.effective_at
        document.expired_at = payload.expired_at
        document.is_deleted = False
        document.deleted_at = None

        await self.db.flush()
        await self._replace_chunks(document, payload)
        await self.db.flush()
        return document

    async def _get_existing_document(
        self,
        source_type: str,
        source_id: UUID | None,
    ) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.source_type == source_type,
            KnowledgeDocument.source_id == source_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _replace_chunks(
        self,
        document: KnowledgeDocument,
        payload: KnowledgeDocumentPayload,
    ) -> None:
        result = await self.db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
        )
        active_chunks = [chunk for chunk in result.scalars().all() if not chunk.is_deleted]
        existing_by_hash = {chunk.content_hash: chunk for chunk in active_chunks}
        desired = [chunk.finalized() for chunk in payload.chunks]
        desired_hashes = {chunk.content_hash for chunk in desired}
        now = datetime.now(UTC)

        for chunk in active_chunks:
            if chunk.content_hash not in desired_hashes:
                chunk.is_deleted = True
                chunk.deleted_at = now

        for chunk_payload in desired:
            chunk = existing_by_hash.get(chunk_payload.content_hash)
            if chunk is None:
                chunk = KnowledgeChunk(document_id=document.id)
                self.db.add(chunk)
            chunk.product_id = payload.product_id
            chunk.category_id = payload.category_id
            chunk.brand_id = payload.brand_id
            chunk.chunk_index = chunk_payload.chunk_index
            chunk.section_path = chunk_payload.section_path
            chunk.page_from = chunk_payload.page_from
            chunk.page_to = chunk_payload.page_to
            chunk.chunk_type = chunk_payload.chunk_type
            chunk.chunk_text = chunk_payload.chunk_text
            chunk.normalized_text = chunk_payload.normalized_text
            chunk.token_count = chunk_payload.token_count
            chunk.embedding = chunk_payload.embedding
            chunk.embedding_model = chunk_payload.embedding_model
            chunk.embedding_version = chunk_payload.embedding_version
            chunk.content_hash = chunk_payload.content_hash
            chunk.metadata_json = chunk_payload.metadata
            chunk.is_deleted = False
            chunk.deleted_at = None
