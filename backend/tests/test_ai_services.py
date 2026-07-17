"""Tests for AI recommendation and polish services.

Pure unit tests — they do NOT touch the database.
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.exceptions import AIAdapterInvalidResponseError, AIAdapterTimeoutError
from app.schemas.ai import AIStatus, PolishRequest, RecommendFilter, RecommendRequest, StockStatus
from app.services.polish import PolishService
from app.services.recommend import RecommendService


# ===================================================================
# Schema validation tests
# ===================================================================
class TestRecommendFilterSchema:
    def test_valid_minimal(self):
        f = RecommendFilter()
        assert f.category_id is None
        assert f.max_face_price is None
        assert f.tag_ids == []
        assert f.keywords == []
        assert f.stock_status is None

    def test_valid_full(self):
        from uuid import uuid4

        cat_id = uuid4()
        tag_id = uuid4()
        f = RecommendFilter(
            category_id=cat_id,
            max_face_price=99.99,
            tag_ids=[tag_id],
            keywords=["wireless", "bluetooth"],
            stock_status=StockStatus.in_stock,
        )
        assert f.category_id == cat_id
        assert f.max_face_price == 99.99
        assert f.tag_ids == [tag_id]
        assert f.keywords == ["wireless", "bluetooth"]
        assert f.stock_status == StockStatus.in_stock

    def test_rejects_negative_price(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendFilter(max_face_price=-1)

    def test_rejects_extra_fields(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendFilter(unknown_field="bad")

    def test_rejects_invalid_stock_status(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendFilter(stock_status="invalid")

    def test_rejects_non_uuid_category(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendFilter(category_id="not-a-uuid")

    def test_rejects_empty_keyword(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendFilter(keywords=[""])

    def test_rejects_too_long_keyword(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendFilter(keywords=["x" * 101])


class TestRecommendRequestSchema:
    def test_valid(self):
        r = RecommendRequest(requirement="I need wireless headphones")
        assert r.requirement == "I need wireless headphones"
        assert r.limit == 20

    def test_rejects_empty_requirement(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendRequest(requirement="")

    def test_rejects_too_long_requirement(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendRequest(requirement="x" * 1001)

    def test_rejects_extra_fields(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendRequest(requirement="test", unknown="bad")

    def test_limit_bounds(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendRequest(requirement="test", limit=0)
        with pytest.raises(ValidationError):
            RecommendRequest(requirement="test", limit=101)


class TestPolishRequestSchema:
    def test_valid(self):
        p = PolishRequest(
            summary="Great products",
            item_reasons=["Reason 1", "Reason 2"],
            industry_phrases=["Phrase 1"],
        )
        assert len(p.item_reasons) == 2
        assert len(p.industry_phrases) == 1

    def test_rejects_empty_summary(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PolishRequest(summary="", item_reasons=["r"], industry_phrases=["p"])

    def test_rejects_extra_fields(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PolishRequest(
                summary="ok",
                item_reasons=["r"],
                industry_phrases=["p"],
                extra="bad",
            )


# ===================================================================
# RecommendService tests
# ===================================================================
class TestRecommendService:
    @pytest.fixture
    def mock_adapter(self):
        adapter = MagicMock()
        adapter.chat = AsyncMock()
        return adapter

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_adapter, mock_db):
        return RecommendService(mock_adapter, mock_db, model="gpt-4o-mini")

    def _mock_ai_answer(self, mock_adapter, payload: dict):
        mock_adapter.chat.return_value = {"answer": json.dumps(payload)}

    def _mock_db_products(self, mock_db, products: list):
        mock_scalar = MagicMock()
        mock_scalar.all.return_value = products
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalar
        mock_db.execute.return_value = mock_result

    def _make_product(self, **overrides):
        from uuid import uuid4

        p = MagicMock()
        p.id = uuid4()
        p.product_no = "P001"
        p.product_name = "Test Product"
        p.brand_id = uuid4()
        p.category_id = uuid4()
        p.face_price = 50.0
        p.cost_price = 30.0
        p.supplier_id = uuid4()
        p.material = "plastic"
        p.stock_status = "in_stock"
        p.description = "A test product"
        for k, v in overrides.items():
            setattr(p, k, v)
        return p

    @pytest.mark.anyio
    async def test_success_with_valid_ai_output(self, service, mock_adapter, mock_db):
        from uuid import uuid4

        cat_id = uuid4()
        self._mock_ai_answer(
            mock_adapter,
            {
                "category_id": str(cat_id),
                "max_face_price": 100,
                "tag_ids": [],
                "keywords": ["wireless"],
                "stock_status": "in_stock",
                "rationale": "Based on your needs",
            },
        )
        self._mock_db_products(mock_db, [])

        result = await service.recommend(
            "I need wireless products",
            {"role_code": "admin"},
            limit=10,
        )

        assert result["status"] == AIStatus.success.value
        assert result["total"] == 0
        assert result["rationale"] == "Based on your needs"
        assert result["filters_applied"]["category_id"] == str(cat_id)
        assert result["filters_applied"]["max_face_price"] == 100
        assert result["filters_applied"]["stock_status"] == "in_stock"

    @pytest.mark.anyio
    async def test_parse_failed_on_malformed_json(self, service, mock_adapter):
        mock_adapter.chat.return_value = {"answer": "This is not JSON at all"}

        result = await service.recommend("test", {"role_code": "admin"})

        assert result["status"] == AIStatus.parse_failed.value
        assert result["total"] == 0
        assert result["products"] == []

    @pytest.mark.anyio
    async def test_parse_failed_on_extra_fields(self, service, mock_adapter, mock_db):
        mock_adapter.chat.return_value = {
            "answer": json.dumps(
                {
                    "category_id": None,
                    "unknown_field": "should be rejected",
                }
            )
        }
        self._mock_db_products(mock_db, [])

        result = await service.recommend("test", {"role_code": "admin"})

        assert result["status"] == AIStatus.parse_failed.value
        assert result["total"] == 0

    @pytest.mark.anyio
    async def test_degraded_on_adapter_failure(self, service, mock_adapter):
        mock_adapter.chat.side_effect = AIAdapterTimeoutError("timeout")

        result = await service.recommend("test", {"role_code": "admin"})

        assert result["status"] == AIStatus.degraded.value
        assert result["total"] == 0

    @pytest.mark.anyio
    async def test_parse_failed_on_empty_answer(self, service, mock_adapter):
        mock_adapter.chat.return_value = {"answer": ""}

        result = await service.recommend("test", {"role_code": "admin"})

        assert result["status"] == AIStatus.parse_failed.value
        assert result["total"] == 0

    @pytest.mark.anyio
    async def test_filters_sensitive_fields_for_sales(self, service, mock_adapter, mock_db):
        self._mock_ai_answer(
            mock_adapter,
            {
                "category_id": None,
                "max_face_price": None,
                "tag_ids": [],
                "keywords": [],
                "stock_status": None,
                "rationale": "test",
            },
        )
        product = self._make_product()
        self._mock_db_products(mock_db, [product])

        result = await service.recommend("test", {"role_code": "sales"})

        assert result["status"] == AIStatus.success.value
        products = result["products"]
        assert len(products) == 1
        assert "cost_price" not in products[0]
        assert "supplier_id" not in products[0]
        assert products[0]["_verified"] is True
        assert products[0]["_verified_by"] == "business_api"

    @pytest.mark.anyio
    async def test_admin_sees_all_fields(self, service, mock_adapter, mock_db):
        self._mock_ai_answer(
            mock_adapter,
            {
                "category_id": None,
                "max_face_price": None,
                "tag_ids": [],
                "keywords": [],
                "stock_status": None,
                "rationale": "test",
            },
        )
        product = self._make_product()
        self._mock_db_products(mock_db, [product])

        result = await service.recommend("test", {"role_code": "admin"}, role_code="admin")

        products = result["products"]
        assert len(products) == 1
        assert "cost_price" in products[0]
        assert "supplier_id" in products[0]

    @pytest.mark.anyio
    async def test_viewer_sees_no_sensitive_fields(self, service, mock_adapter, mock_db):
        self._mock_ai_answer(
            mock_adapter,
            {
                "category_id": None,
                "max_face_price": None,
                "tag_ids": [],
                "keywords": [],
                "stock_status": None,
                "rationale": "test",
            },
        )
        product = self._make_product()
        self._mock_db_products(mock_db, [product])

        result = await service.recommend("test", {"role_code": "viewer"})

        products = result["products"]
        assert len(products) == 1
        assert "cost_price" not in products[0]
        assert "supplier_id" not in products[0]

    @pytest.mark.anyio
    async def test_invalid_stock_status_returns_parse_failed(self, service, mock_adapter):
        mock_adapter.chat.return_value = {
            "answer": json.dumps(
                {
                    "category_id": None,
                    "max_face_price": None,
                    "tag_ids": [],
                    "keywords": [],
                    "stock_status": "invalid_status",
                    "rationale": "test",
                }
            )
        }

        result = await service.recommend("test", {"role_code": "admin"})

        assert result["status"] == AIStatus.parse_failed.value
        assert result["total"] == 0

    @pytest.mark.anyio
    async def test_negative_price_returns_parse_failed(self, service, mock_adapter):
        mock_adapter.chat.return_value = {
            "answer": json.dumps(
                {
                    "category_id": None,
                    "max_face_price": -10,
                    "tag_ids": [],
                    "keywords": [],
                    "stock_status": None,
                    "rationale": "test",
                }
            )
        }

        result = await service.recommend("test", {"role_code": "admin"})

        assert result["status"] == AIStatus.parse_failed.value
        assert result["total"] == 0


# ===================================================================
# PolishService tests
# ===================================================================
class TestPolishService:
    @pytest.fixture
    def mock_adapter(self):
        adapter = MagicMock()
        adapter.chat = AsyncMock()
        return adapter

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_adapter, mock_db):
        return PolishService(mock_adapter, mock_db, model="gpt-4o-mini")

    def _make_proposal(self, item_count=2):
        from uuid import uuid4

        proposal = MagicMock()
        proposal.id = uuid4()
        proposal.proposal_name = "Test Proposal"
        proposal.customer_name = "John Doe"
        proposal.ai_polished = False
        proposal.ai_polish_content = None
        proposal.ai_polish_at = None
        proposal.ai_polish_model = None

        items = []
        for i in range(item_count):
            item = MagicMock()
            item.quantity = 1
            item.remark = f"Remark {i}"
            product = MagicMock()
            product.product_name = f"Product {i}"
            product.face_price = 100.0
            product.material = "metal"
            product.description = f"Desc {i}"
            item.product = product
            items.append(item)
        proposal.items = items
        return proposal

    def _mock_ai_answer(self, mock_adapter, payload: dict):
        mock_adapter.chat.return_value = {"answer": json.dumps(payload)}

    def _mock_db_proposal(self, mock_db, proposal):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = proposal
        mock_db.execute.return_value = mock_result

    @pytest.fixture
    def _sql_mocks(self):
        """Mock sqlalchemy select/selectinload to avoid ORM class registry resolution."""
        mock_loader = MagicMock()
        mock_loader.selectinload.return_value = MagicMock()

        mock_query = MagicMock()
        mock_query.options.return_value = mock_query
        mock_query.where.return_value = mock_query

        with patch("app.services.polish.select", return_value=mock_query), patch(
            "app.services.polish.selectinload", return_value=mock_loader
        ):
            yield

    @pytest.mark.anyio
    async def test_success_with_valid_ai_output(self, service, mock_adapter, mock_db, _sql_mocks):
        proposal = self._make_proposal(item_count=2)
        self._mock_db_proposal(mock_db, proposal)
        self._mock_ai_answer(
            mock_adapter,
            {
                "summary": "Great selection",
                "item_reasons": ["Reason 1", "Reason 2"],
                "industry_phrases": ["Phrase 1"],
            },
        )

        result = await service.polish_proposal(proposal.id, {"role_code": "admin"})

        assert result["status"] == AIStatus.success.value
        assert result["summary"] == "Great selection"
        assert len(result["item_reasons"]) == 2
        assert proposal.ai_polished is True
        assert proposal.ai_polish_content is not None
        mock_db.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_failure_on_adapter_timeout(self, service, mock_adapter, mock_db, _sql_mocks):
        proposal = self._make_proposal(item_count=2)
        self._mock_db_proposal(mock_db, proposal)
        mock_adapter.chat.side_effect = AIAdapterTimeoutError("timeout")

        with pytest.raises(AIAdapterTimeoutError):
            await service.polish_proposal(proposal.id, {"role_code": "admin"})

        assert proposal.ai_polished is False
        mock_db.commit.assert_not_awaited()

    @pytest.mark.anyio
    async def test_failure_on_invalid_json(self, service, mock_adapter, mock_db, _sql_mocks):
        proposal = self._make_proposal(item_count=2)
        self._mock_db_proposal(mock_db, proposal)
        mock_adapter.chat.return_value = {"answer": "not json"}

        with pytest.raises(AIAdapterInvalidResponseError, match="格式错误"):
            await service.polish_proposal(proposal.id, {"role_code": "admin"})

        assert proposal.ai_polished is False
        mock_db.commit.assert_not_awaited()

    @pytest.mark.anyio
    async def test_failure_on_empty_answer(self, service, mock_adapter, mock_db, _sql_mocks):
        proposal = self._make_proposal(item_count=2)
        self._mock_db_proposal(mock_db, proposal)
        mock_adapter.chat.return_value = {"answer": ""}

        with pytest.raises(AIAdapterInvalidResponseError, match="未返回内容"):
            await service.polish_proposal(proposal.id, {"role_code": "admin"})

        assert proposal.ai_polished is False
        mock_db.commit.assert_not_awaited()

    @pytest.mark.anyio
    async def test_failure_on_mismatched_item_count(
        self, service, mock_adapter, mock_db, _sql_mocks
    ):
        proposal = self._make_proposal(item_count=3)
        self._mock_db_proposal(mock_db, proposal)
        mock_adapter.chat.return_value = {
            "answer": json.dumps(
                {
                    "summary": "Great",
                    "item_reasons": ["Only one reason"],
                    "industry_phrases": ["Phrase"],
                }
            )
        }

        with pytest.raises(AIAdapterInvalidResponseError, match="不匹配"):
            await service.polish_proposal(proposal.id, {"role_code": "admin"})

        assert proposal.ai_polished is False
        mock_db.commit.assert_not_awaited()

    @pytest.mark.anyio
    async def test_failure_on_extra_fields_in_ai_output(
        self, service, mock_adapter, mock_db, _sql_mocks
    ):
        proposal = self._make_proposal(item_count=1)
        self._mock_db_proposal(mock_db, proposal)
        mock_adapter.chat.return_value = {
            "answer": json.dumps(
                {
                    "summary": "Good",
                    "item_reasons": ["Reason"],
                    "industry_phrases": ["Phrase"],
                    "extra_forbidden_field": "bad",
                }
            )
        }

        with pytest.raises(AIAdapterInvalidResponseError, match="校验失败"):
            await service.polish_proposal(proposal.id, {"role_code": "admin"})

        assert proposal.ai_polished is False
        mock_db.commit.assert_not_awaited()

    @pytest.mark.anyio
    async def test_prompt_excludes_customer_name(self, service, mock_adapter, mock_db, _sql_mocks):
        proposal = self._make_proposal(item_count=1)
        proposal.customer_name = "Secret Customer"
        self._mock_db_proposal(mock_db, proposal)
        self._mock_ai_answer(
            mock_adapter,
            {
                "summary": "Good",
                "item_reasons": ["Reason"],
                "industry_phrases": ["Phrase"],
            },
        )

        await service.polish_proposal(proposal.id, {"role_code": "admin"})

        call_args = mock_adapter.chat.call_args
        prompt = call_args.kwargs["message"]
        assert "Secret Customer" not in prompt

    @pytest.mark.anyio
    async def test_no_cost_or_supplier_in_prompt(self, service, mock_adapter, mock_db, _sql_mocks):
        proposal = self._make_proposal(item_count=1)
        self._mock_db_proposal(mock_db, proposal)
        self._mock_ai_answer(
            mock_adapter,
            {
                "summary": "Good",
                "item_reasons": ["Reason"],
                "industry_phrases": ["Phrase"],
            },
        )

        await service.polish_proposal(proposal.id, {"role_code": "admin"})

        call_args = mock_adapter.chat.call_args
        prompt = call_args.kwargs["message"]
        match = re.search(r"产品清单：\n(.+)", prompt, re.DOTALL)
        assert match is not None
        items_json = json.loads(match.group(1))
        for item in items_json:
            assert "cost_price" not in item
            assert "supplier_id" not in item

    @pytest.mark.anyio
    async def test_repeat_allowed(self, service, mock_adapter, mock_db, _sql_mocks):
        """Calling polish twice should succeed both times."""
        proposal = self._make_proposal(item_count=1)
        self._mock_db_proposal(mock_db, proposal)
        self._mock_ai_answer(
            mock_adapter,
            {
                "summary": "First polish",
                "item_reasons": ["Reason"],
                "industry_phrases": ["Phrase"],
            },
        )

        result1 = await service.polish_proposal(proposal.id, {"role_code": "admin"})
        assert result1["status"] == AIStatus.success.value
        assert proposal.ai_polished is True

        mock_adapter.chat.return_value = {
            "answer": json.dumps(
                {
                    "summary": "Second polish",
                    "item_reasons": ["New reason"],
                    "industry_phrases": ["New phrase"],
                }
            )
        }

        result2 = await service.polish_proposal(proposal.id, {"role_code": "admin"})
        assert result2["status"] == AIStatus.success.value
        assert result2["summary"] == "Second polish"
