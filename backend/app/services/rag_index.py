from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Float, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AIServiceAdapter
from app.adapters.exceptions import AIAdapterDimensionMismatchError
from app.adapters.factory import get_ai_adapter
from app.core.config import settings
from app.models.doc_chunk import ProductManualChunk
from app.models.product import ProductManual


def split_text(text: str, chunk_size: int = 600, overlap: int = 80) -> list[dict]:
    """Split text into overlapping chunks.

    :param text: Input text to split.
    :param chunk_size: Maximum characters per chunk.
    :param overlap: Number of characters to overlap between consecutive chunks.
    :return: List of dicts with ``chunk_index``, ``chunk_text``, ``chunk_tokens``.
    """
    if not text or chunk_size <= 0:
        return []
    if len(text) <= chunk_size:
        return [{"chunk_index": 0, "chunk_text": text, "chunk_tokens": len(text)}]
    chunks = []
    start = 0
    index = 0
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        chunks.append(
            {
                "chunk_index": index,
                "chunk_text": chunk_text,
                "chunk_tokens": len(chunk_text),
            }
        )
        start = end - overlap
        if start >= len(text):
            break
        index += 1
    return chunks


class RagIndexer:
    """RAG indexer for ProductManual documents.

    Manages the full lifecycle of indexing a manual:
    1. Loads the manual and validates it has parsed content.
    2. Transitions state to ``processing``.
    3. Splits content into chunks (configurable size/overlap).
    4. Computes embeddings via the AI adapter.
    5. Validates embedding count matches chunk count and dimension is correct.
    6. Deletes old chunks and inserts new ones in a single transaction.
    7. Updates manual state to ``indexed`` or ``failed``.

    Idempotent: if the manual's ``content_hash`` matches the hash of the current
    parsed content, indexing is skipped (returns 0 without touching chunks).
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.db = db
        self.chunk_size = chunk_size or settings.AI_RAG_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.AI_RAG_CHUNK_OVERLAP

    async def _load_manual(self, product_manual_id: UUID) -> ProductManual:
        result = await self.db.execute(
            select(ProductManual).where(ProductManual.id == product_manual_id)
        )
        manual = result.scalar_one_or_none()
        if not manual:
            raise ValueError(f"ProductManual {product_manual_id} not found")
        return manual

    async def _set_status(
        self,
        manual: ProductManual,
        status: str,
        error: str | None = None,
    ) -> None:
        manual.index_status = status
        manual.index_error = error
        if status == "indexed":
            manual.last_indexed_at = datetime.now(UTC)
        elif status == "failed":
            manual.last_indexed_at = None
        await self.db.flush()

    def _compute_content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _compute_chunk_hash(self, chunk_text: str) -> str:
        return hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()

    async def _validate_embeddings(
        self,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        if len(embeddings) != len(chunks):
            raise ValueError(
                f"Embedding count ({len(embeddings)}) does not match "
                f"chunk count ({len(chunks)})"
            )
        expected_dim = settings.AI_EMBEDDING_DIM
        for i, vec in enumerate(embeddings):
            if len(vec) != expected_dim:
                raise AIAdapterDimensionMismatchError(
                    f"Embedding {i} has dimension {len(vec)}, expected {expected_dim}"
                )

    async def _delete_old_chunks(self, manual: ProductManual) -> None:
        await self.db.execute(
            delete(ProductManualChunk).where(
                ProductManualChunk.product_manual_id == manual.id
            )
        )

    async def _insert_chunks(
        self,
        manual: ProductManual,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        for i, chunk_data in enumerate(chunks):
            chunk = ProductManualChunk(
                product_manual_id=manual.id,
                product_id=manual.product_id,
                chunk_index=chunk_data["chunk_index"],
                chunk_text=chunk_data["chunk_text"],
                chunk_tokens=chunk_data["chunk_tokens"],
                chunk_hash=self._compute_chunk_hash(chunk_data["chunk_text"]),
                embedding=embeddings[i],
            )
            self.db.add(chunk)

    async def index_manual(
        self,
        product_manual_id: UUID,
        adapter: AIServiceAdapter | None = None,
    ) -> int:
        """Index a single ProductManual.

        Returns the number of chunks indexed. Returns 0 (without error) when
        the manual has no parsed content or is already indexed with identical
        content (idempotent skip).

        :raises ValueError: if the manual does not exist.
        :raises AIAdapterDimensionMismatchError: if embedding dimensions differ.
        :raises RuntimeError: if embedding count != chunk count.
        """
        if adapter is None:
            adapter = get_ai_adapter()

        manual = await self._load_manual(product_manual_id)
        content = manual.parsed_content or ""
        if not content:
            return 0

        content_hash = self._compute_content_hash(content)
        if manual.content_hash == content_hash and manual.index_status == "indexed":
            return 0

        await self._set_status(manual, "processing")

        try:
            chunks = split_text(content, self.chunk_size, self.chunk_overlap)
            if not chunks:
                await self._set_status(manual, "indexed")
                manual.content_hash = content_hash
                await self.db.commit()
                return 0

            texts = [c["chunk_text"] for c in chunks]
            embeddings = await adapter.embed(texts)
            await self._validate_embeddings(chunks, embeddings)

            await self._delete_old_chunks(manual)
            await self._insert_chunks(manual, chunks, embeddings)

            manual.content_hash = content_hash
            await self._set_status(manual, "indexed")
            await self.db.commit()
            return len(chunks)

        except Exception as exc:
            # Roll back the replacement transaction so previously indexed
            # chunks remain available; failure status is persisted separately.
            await self.db.rollback()
            manual = await self._load_manual(product_manual_id)
            await self._set_status(manual, "failed", str(exc)[:1000])
            await self.db.commit()
            raise


class RagSearcher:
    """Semantic search over indexed ProductManual chunks.

    :param top_k: Maximum number of chunks to return.
    :param min_score: Minimum similarity score (1 - cosine distance) to include.
    """

    def __init__(
        self,
        adapter: AIServiceAdapter,
        db: AsyncSession,
        *,
        top_k: int = 8,
        min_score: float = 0.65,
    ):
        self.adapter = adapter
        self.db = db
        self.top_k = top_k
        self.min_score = min_score

    async def search(
        self,
        query: str,
        *,
        product_id: UUID | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> list[dict]:
        """Search for chunks matching the query.

        :param query: Search query text.
        :param product_id: Optional filter to a single product's chunks.
        :param top_k: Override default top_k.
        :param min_score: Override default min_score.
        :return: List of chunk dicts with traceability fields.
        """
        vec = await self.adapter.embed_one(query)
        if not vec:
            return []

        k = top_k if top_k is not None else self.top_k
        threshold = min_score if min_score is not None else self.min_score

        distance = ProductManualChunk.embedding.op("<=>", return_type=Float)(vec).label("distance")
        stmt = select(distance, ProductManualChunk).where(
            ProductManualChunk.is_deleted.is_(False)
        )
        if product_id:
            stmt = stmt.where(ProductManualChunk.product_id == product_id)
        stmt = stmt.order_by(distance).limit(k)
        result = await self.db.execute(stmt)
        rows = result.all()

        out: list[dict] = []
        for dist, chunk in rows:
            score = 1.0 - float(dist) if dist is not None else 0.0
            if score < threshold:
                continue
            out.append(
                {
                    "chunk_id": str(chunk.id),
                    "product_id": str(chunk.product_id),
                    "product_manual_id": str(chunk.product_manual_id),
                    "chunk_index": chunk.chunk_index,
                    "chunk_text": chunk.chunk_text,
                    "score": round(score, 4),
                }
            )
        return out
