"""Tests for manual-related Pydantic schemas."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.manuals import (
    ProductManualCreate,
    RagAnswerRequest,
    RagAnswerResponse,
)


class TestProductManualCreate:
    def test_minimal_required(self):
        body = ProductManualCreate(
            product_id=uuid4(),
            attachment_id=uuid4(),
        )
        assert body.doc_type == "manual"
        assert body.parsed_content is None

    def test_with_parsed_content(self):
        body = ProductManualCreate(
            product_id=uuid4(),
            attachment_id=uuid4(),
            doc_type="spec",
            parsed_content="extracted text",
        )
        assert body.doc_type == "spec"
        assert body.parsed_content == "extracted text"

    def test_rejects_invalid_doc_type(self):
        with pytest.raises(ValidationError):
            ProductManualCreate(
                product_id=uuid4(),
                attachment_id=uuid4(),
                doc_type="invalid_type",
            )


class TestRagAnswerRequest:
    def test_defaults(self):
        body = RagAnswerRequest(query="what is the warranty?")
        assert body.top_k == 8
        assert body.min_score == 0.65
        assert body.product_id is None

    def test_top_k_bounds(self):
        with pytest.raises(ValidationError):
            RagAnswerRequest(query="q", top_k=0)
        with pytest.raises(ValidationError):
            RagAnswerRequest(query="q", top_k=100)

    def test_min_score_bounds(self):
        with pytest.raises(ValidationError):
            RagAnswerRequest(query="q", min_score=-0.1)
        with pytest.raises(ValidationError):
            RagAnswerRequest(query="q", min_score=1.1)


class TestRagAnswerResponse:
    def test_defaults(self):
        body = RagAnswerResponse(answer="hello")
        assert body.bounded is True
        assert body.insufficient_sources is False
        assert body.sources == []

    def test_with_sources(self):
        body = RagAnswerResponse(
            answer="The warranty is 1 year.",
            sources=[
                {
                    "chunk_id": str(uuid4()),
                    "product_manual_id": str(uuid4()),
                    "product_id": str(uuid4()),
                    "chunk_index": 0,
                    "chunk_text": "1 year warranty",
                    "score": 0.85,
                }
            ],
            bounded=True,
            insufficient_sources=False,
        )
        assert len(body.sources) == 1
