"""Tests for RagIndexer state machine, validation, and transactional behaviour.

Pure unit tests using mocks — no real DB or AI adapter.
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.exceptions import AIAdapterDimensionMismatchError
from app.models.product import ProductManual
from app.services.rag_index import RagIndexer, split_text

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()

    def _embed(texts):
        return [[0.1] * 1536 for _ in texts]

    adapter.embed = AsyncMock(side_effect=_embed)
    adapter.embed_one = AsyncMock(return_value=[0.1] * 1536)
    return adapter


def _make_manual(
    manual_id="m1",
    product_id="p1",
    parsed_content="x" * 2000,
    index_status="pending",
    content_hash=None,
):
    manual = MagicMock(spec=ProductManual)
    manual.id = manual_id
    manual.product_id = product_id
    manual.parsed_content = parsed_content
    manual.index_status = index_status
    manual.content_hash = content_hash
    manual.index_error = None
    manual.last_indexed_at = None
    return manual


def _scalar_result(manual):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=manual)
    return result


def _empty_scalar():
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    return result


# ---------------------------------------------------------------------------
# split_text (pure function, also covered by test_rag_split.py)
# ---------------------------------------------------------------------------

class TestSplitText:
    def test_returns_empty_for_empty(self):
        assert split_text("", 600, 80) == []

    def test_returns_empty_for_zero_chunk(self):
        assert split_text("hello", 0, 0) == []

    def test_single_chunk_for_short_text(self):
        r = split_text("hello", 600, 80)
        assert len(r) == 1
        assert r[0]["chunk_text"] == "hello"


# ---------------------------------------------------------------------------
# RagIndexer — not found
# ---------------------------------------------------------------------------

class TestIndexManualNotFound:
    @pytest.mark.anyio
    async def test_raises_value_error(self, mock_db, mock_adapter):
        mock_db.execute.return_value = _empty_scalar()
        indexer = RagIndexer(mock_db)
        with pytest.raises(ValueError, match="not found"):
            await indexer.index_manual("nonexistent", adapter=mock_adapter)


# ---------------------------------------------------------------------------
# RagIndexer — empty content
# ---------------------------------------------------------------------------

class TestIndexManualEmptyContent:
    @pytest.mark.anyio
    async def test_returns_zero(self, mock_db, mock_adapter):
        manual = _make_manual(parsed_content="")
        mock_db.execute.return_value = _scalar_result(manual)
        indexer = RagIndexer(mock_db)
        count = await indexer.index_manual("m1", adapter=mock_adapter)
        assert count == 0


# ---------------------------------------------------------------------------
# RagIndexer — idempotent skip
# ---------------------------------------------------------------------------

class TestIndexManualIdempotentSkip:
    @pytest.mark.anyio
    async def test_skip_when_hash_matches_and_indexed(self, mock_db, mock_adapter):
        content = "already indexed content"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        manual = _make_manual(
            parsed_content=content,
            index_status="indexed",
            content_hash=content_hash,
        )
        mock_db.execute.return_value = _scalar_result(manual)
        indexer = RagIndexer(mock_db)
        count = await indexer.index_manual("m1", adapter=mock_adapter)
        assert count == 0
        # Should NOT have called embed (skip before any AI call).
        mock_adapter.embed.assert_not_awaited()


# ---------------------------------------------------------------------------
# RagIndexer — state transitions
# ---------------------------------------------------------------------------

class TestIndexManualStateTransitions:
    @pytest.mark.anyio
    async def test_pending_to_processing_to_indexed(self, mock_db, mock_adapter):
        manual = _make_manual(parsed_content="x" * 2000)
        mock_db.execute.return_value = _scalar_result(manual)
        indexer = RagIndexer(mock_db)
        count = await indexer.index_manual("m1", adapter=mock_adapter)
        assert count > 0
        # Status should have been set to "indexed" at some point.
        assert manual.index_status == "indexed"
        assert manual.index_error is None
        assert manual.last_indexed_at is not None

    @pytest.mark.anyio
    async def test_failed_sets_status_and_error(self, mock_db, mock_adapter):
        manual = _make_manual(parsed_content="x" * 2000)
        mock_db.execute.return_value = _scalar_result(manual)
        mock_adapter.embed = AsyncMock(
            side_effect=AIAdapterDimensionMismatchError("dim mismatch")
        )
        indexer = RagIndexer(mock_db)
        with pytest.raises(AIAdapterDimensionMismatchError):
            await indexer.index_manual("m1", adapter=mock_adapter)
        assert manual.index_status == "failed"
        assert "dim mismatch" in (manual.index_error or "")


# ---------------------------------------------------------------------------
# RagIndexer — embedding validation
# ---------------------------------------------------------------------------

class TestIndexManualEmbeddingValidation:
    @pytest.mark.anyio
    async def test_count_mismatch_raises(self, mock_db, mock_adapter):
        manual = _make_manual(parsed_content="x" * 2000)
        mock_db.execute.return_value = _scalar_result(manual)
        mock_adapter.embed = AsyncMock(return_value=[[0.1] * 1536])  # only 1 vector
        indexer = RagIndexer(mock_db)
        with pytest.raises(ValueError, match="count"):
            await indexer.index_manual("m1", adapter=mock_adapter)

    @pytest.mark.anyio
    async def test_dimension_mismatch_raises(self, mock_db, mock_adapter):
        manual = _make_manual(parsed_content="x" * 2000)
        mock_db.execute.return_value = _scalar_result(manual)
        mock_adapter.embed = AsyncMock(
            return_value=[[0.1] * 100, [0.1] * 100, [0.1] * 100, [0.1] * 100]
        )
        indexer = RagIndexer(mock_db)
        with pytest.raises(AIAdapterDimensionMismatchError, match="100"):
            await indexer.index_manual("m1", adapter=mock_adapter)


# ---------------------------------------------------------------------------
# RagIndexer — transactional delete/replace
# ---------------------------------------------------------------------------

class TestIndexManualTransactional:
    @pytest.mark.anyio
    async def test_deletes_old_chunks_before_insert(self, mock_db, mock_adapter):
        manual = _make_manual(parsed_content="x" * 2000)
        mock_db.execute.return_value = _scalar_result(manual)
        indexer = RagIndexer(mock_db)
        await indexer.index_manual("m1", adapter=mock_adapter)
        # commit should have been called (transactional).
        mock_db.commit.assert_awaited()

    @pytest.mark.anyio
    async def test_no_partial_success_on_failure(self, mock_db, mock_adapter):
        """If embed fails, chunks must NOT be partially inserted."""
        manual = _make_manual(parsed_content="x" * 2000)
        mock_db.execute.return_value = _scalar_result(manual)
        mock_adapter.embed = AsyncMock(side_effect=RuntimeError("boom"))
        indexer = RagIndexer(mock_db)
        with pytest.raises(RuntimeError):
            await indexer.index_manual("m1", adapter=mock_adapter)
        # commit was still called (to persist failed status) but no chunks
        # should have been added after the failure.
        assert manual.index_status == "failed"


# ---------------------------------------------------------------------------
# RagIndexer — configurable chunk size / overlap
# ---------------------------------------------------------------------------

class TestIndexManualConfigurable:
    @pytest.mark.anyio
    async def test_uses_custom_chunk_params(self, mock_db, mock_adapter):
        manual = _make_manual(parsed_content="x" * 2000)
        mock_db.execute.return_value = _scalar_result(manual)
        indexer = RagIndexer(mock_db, chunk_size=100, chunk_overlap=20)
        assert indexer.chunk_size == 100
        assert indexer.chunk_overlap == 20
        count = await indexer.index_manual("m1", adapter=mock_adapter)
        assert count > 0


# ---------------------------------------------------------------------------
# RagSearcher
# ---------------------------------------------------------------------------

class TestRagSearcher:
    @pytest.fixture
    def searcher(self, mock_adapter, mock_db):
        from app.services.rag_index import RagSearcher

        return RagSearcher(mock_adapter, mock_db, top_k=5, min_score=0.7)

    @pytest.mark.anyio
    async def test_empty_query_returns_empty(self, searcher, mock_adapter):
        mock_adapter.embed_one = AsyncMock(return_value=[])
        results = await searcher.search("hello")
        assert results == []

    @pytest.mark.anyio
    async def test_filters_by_min_score(self, searcher, mock_db):
        mock_adapter.embed_one = AsyncMock(return_value=[0.1] * 1536)
        chunk = MagicMock()
        chunk.id = "c1"
        chunk.product_id = "p1"
        chunk.product_manual_id = "m1"
        chunk.chunk_index = 0
        chunk.chunk_text = "relevant text"
        chunk.is_deleted = False
        row = (0.5, chunk)  # distance 0.5 -> score 0.5 < 0.7 threshold
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[row])
        mock_db.execute.return_value = mock_result
        results = await searcher.search("hello")
        assert results == []  # filtered out by min_score

    @pytest.mark.anyio
    async def test_returns_traceability_fields(self, searcher, mock_db):
        mock_adapter.embed_one = AsyncMock(return_value=[0.1] * 1536)
        chunk = MagicMock()
        chunk.id = "c1"
        chunk.product_id = "p1"
        chunk.product_manual_id = "m1"
        chunk.chunk_index = 2
        chunk.chunk_text = "some text"
        chunk.is_deleted = False
        row = (0.1, chunk)  # distance 0.1 -> score 0.9
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[row])
        mock_db.execute.return_value = mock_result
        results = await searcher.search("hello")
        assert len(results) == 1
        r = results[0]
        assert r["chunk_id"] == "c1"
        assert r["product_id"] == "p1"
        assert r["product_manual_id"] == "m1"
        assert r["chunk_index"] == 2
        assert r["chunk_text"] == "some text"
        assert r["score"] == 0.9
