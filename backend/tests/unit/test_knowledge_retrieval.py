from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.none import NoneAdapter
from app.knowledge.citations import CitationValidator
from app.knowledge.errors import KnowledgeGatewayError
from app.knowledge.retrieval.hybrid import HybridRetriever
from app.knowledge.retrieval.rrf import reciprocal_rank_fusion


def test_rrf_merges_channels_and_ranks_highest_first():
    fused = reciprocal_rank_fusion(
        {
            "exact": [{"source_id": "chunk:a"}, {"source_id": "chunk:b"}],
            "keyword": [{"source_id": "chunk:b"}, {"source_id": "chunk:c"}],
        }
    )
    assert fused[0]["source_id"] == "chunk:b"
    assert set(fused[0]["channels"]) == {"exact", "keyword"}


def test_citation_validator_rejects_unknown_source_id_in_answer():
    validator = CitationValidator()
    with pytest.raises(KnowledgeGatewayError) as exc:
        validator.validate_answer("引用 chunk:11111111-1111-1111-1111-111111111111", [])
    assert exc.value.code.value == "CITATION_INVALID"


@pytest.mark.anyio
async def test_hybrid_retriever_searches_documents_for_dynamic_field_question(monkeypatch):
    from app.knowledge.retrieval import hybrid as hybrid_module

    monkeypatch.setattr(hybrid_module, "exact_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(hybrid_module, "keyword_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(hybrid_module, "vector_search", AsyncMock(return_value=[]))
    retriever = HybridRetriever(NoneAdapter(), MagicMock())
    sources, events = await retriever.retrieve(
        "查这个产品库存",
        product_id=None,
        pool=MagicMock(hidden_fields=frozenset()),
        current_user={"role_code": "viewer", "perms": []},
        trace_id="t1",
    )
    assert sources == []
    assert any(event.get("channel") == "exact" for event in events)
    hybrid_module.vector_search.assert_awaited_once()


@pytest.mark.anyio
async def test_hybrid_retriever_fuses_search_results(monkeypatch):
    from app.knowledge.retrieval import hybrid as hybrid_module

    monkeypatch.setattr(
        hybrid_module,
        "exact_search",
        AsyncMock(
            return_value=[
                {
                    "chunk_id": "a",
                    "document_id": "d1",
                    "product_id": "p1",
                    "title": "Doc A",
                    "quote": "Q",
                    "section": "1",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        hybrid_module,
        "keyword_search",
        AsyncMock(
            return_value=[
                {
                    "chunk_id": "b",
                    "document_id": "d2",
                    "product_id": "p2",
                    "title": "Doc B",
                    "quote": "Q2",
                    "section": "2",
                }
            ]
        ),
    )
    monkeypatch.setattr(hybrid_module, "vector_search", AsyncMock(return_value=[]))
    retriever = HybridRetriever(MagicMock(), MagicMock())
    sources, events = await retriever.retrieve(
        "A100 安装",
        product_id=None,
        pool=MagicMock(hidden_fields=frozenset()),
        current_user={"role_code": "viewer", "perms": []},
        trace_id="t1",
    )
    assert len(sources) == 2
    assert sources[0]["source_id"].startswith("chunk:")
    assert any(event.get("channel") == "exact" for event in events)
