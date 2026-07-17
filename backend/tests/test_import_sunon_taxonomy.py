"""Tests for app/scripts/import_sunon_taxonomy.py.

Pure unit tests for normalization/validation (no DB).
AsyncMock-based tests for the DB upsert layer.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 使 backend/ 可被导入
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.scripts.import_sunon_taxonomy import (  # noqa: E402
    SUPPLIER_NAME,
    TAG_TYPE_SERIES,
    TaxonomyValidationError,
    _get_or_create_category,
    _get_or_create_supplier,
    _get_or_create_tag,
    import_taxonomy,
    normalize_name,
    validate_and_normalize,
)

# ---------------------------------------------------------------------------
# Pure normalization / validation tests
# ---------------------------------------------------------------------------


class TestNormalizeName:
    def test_trims_whitespace(self):
        assert normalize_name("  办公椅  ") == "办公椅"

    def test_collapses_internal_whitespace(self):
        assert normalize_name("维度  X") == "维度 X"

    def test_converts_non_string(self):
        assert normalize_name(123) == "123"

    def test_empty_after_normalize(self):
        assert normalize_name("   ") == ""


class TestValidateAndNormalize:
    def _make_raw(self, categories=None, series=None):
        return {
            "大类": categories or {"坐具": {"小类": ["办公椅", "访客椅"]}},
            "系列_品牌": series or ["灵多", "灵多Pro"],
            "meta": {"source": "secret-url", "url": "https://secret", "extracted_at": "2026-01-01"},
        }

    def test_valid_input(self):
        raw = self._make_raw()
        result = validate_and_normalize(raw)
        assert "categories" in result
        assert "series" in result
        assert result["categories"]["坐具"]["children"] == ["办公椅", "访客椅"]
        assert result["series"] == ["灵多", "灵多Pro"]

    def test_meta_is_ignored(self):
        raw = self._make_raw()
        result = validate_and_normalize(raw)
        assert "meta" not in result

    def test_top_level_not_dict_raises(self):
        with pytest.raises(TaxonomyValidationError, match="顶层必须是 JSON 对象"):
            validate_and_normalize(["not", "a", "dict"])

    def test_missing_categories_raises(self):
        with pytest.raises(TaxonomyValidationError, match='"大类" 字段缺失'):
            validate_and_normalize({"系列_品牌": []})

    def test_missing_series_raises(self):
        with pytest.raises(TaxonomyValidationError, match='"系列_品牌" 字段缺失'):
            validate_and_normalize({"大类": {}})

    def test_categories_not_dict_raises(self):
        with pytest.raises(TaxonomyValidationError, match='"大类" 字段缺失'):
            validate_and_normalize({"大类": ["list"]})

    def test_series_not_list_raises(self):
        with pytest.raises(TaxonomyValidationError, match='"系列_品牌" 字段缺失'):
            validate_and_normalize({"大类": {}, "系列_品牌": "string"})

    def test_l1_data_not_dict_raises(self):
        raw = {"大类": {"坐具": "not-a-dict"}, "系列_品牌": []}
        with pytest.raises(TaxonomyValidationError, match='大类 "坐具" 的值必须是对象'):
            validate_and_normalize(raw)

    def test_children_not_list_raises(self):
        raw = {"大类": {"坐具": {"小类": "not-a-list"}}, "系列_品牌": []}
        with pytest.raises(TaxonomyValidationError, match='"小类" 必须是数组'):
            validate_and_normalize(raw)

    def test_duplicate_l2_children_deduplicated(self):
        raw = self._make_raw(categories={"坐具": {"小类": ["办公椅", "办公椅", " 办公椅 "]}})
        result = validate_and_normalize(raw)
        assert result["categories"]["坐具"]["children"] == ["办公椅"]

    def test_duplicate_series_deduplicated(self):
        raw = self._make_raw(series=["灵多", "灵多", " 灵多 "])
        result = validate_and_normalize(raw)
        assert result["series"] == ["灵多"]

    def test_duplicate_l1_merged(self):
        raw = {
            "大类": {
                "坐具": {"小类": ["办公椅"]},
                " 坐具 ": {"小类": ["访客椅"]},
            },
            "系列_品牌": [],
        }
        result = validate_and_normalize(raw)
        children = result["categories"]["坐具"]["children"]
        assert "办公椅" in children
        assert "访客椅" in children
        assert len(children) == 2

    def test_empty_names_skipped(self):
        raw = self._make_raw(categories={"  ": {"小类": ["", "  "]}})
        result = validate_and_normalize(raw)
        assert result["categories"] == {}

    def test_normalizes_all_names(self):
        raw = self._make_raw(
            categories={"  坐具  ": {"小类": [" 办公椅 ", " 访客 椅 "]}}
        )
        result = validate_and_normalize(raw)
        assert "坐具" in result["categories"]
        assert result["categories"]["坐具"]["children"] == ["办公椅", "访客 椅"]


# ---------------------------------------------------------------------------
# DB layer tests using AsyncMock
# ---------------------------------------------------------------------------


def _make_mock_session():
    """创建一个最小 AsyncSession mock，支持 execute().scalar_one_or_none() 和 add/flush."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)

    mock_db = AsyncMock(spec=["execute", "add", "flush", "commit"])
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db, mock_result


class TestGetOrCreateSupplier:
    @pytest.mark.anyio
    async def test_returns_existing(self):
        mock_db, mock_result = _make_mock_session()
        existing = MagicMock(supplier_name=SUPPLIER_NAME)
        mock_result.scalar_one_or_none.return_value = existing

        supplier, created = await _get_or_create_supplier(mock_db)
        assert supplier is existing
        assert created is False
        mock_db.add.assert_not_called()


class TestGetOrCreateCategory:
    @pytest.mark.anyio
    async def test_returns_existing(self):
        mock_db, mock_result = _make_mock_session()
        existing = MagicMock(category_name="办公椅", level=1, parent_id=None)
        mock_result.scalar_one_or_none.return_value = existing

        cat, created = await _get_or_create_category(mock_db, "办公椅", None, 1)
        assert cat is existing
        assert created is False


class TestGetOrCreateTag:
    @pytest.mark.anyio
    async def test_returns_existing(self):
        mock_db, mock_result = _make_mock_session()
        existing = MagicMock(tag_name="灵多", tag_type=TAG_TYPE_SERIES)
        mock_result.scalar_one_or_none.return_value = existing

        tag, created = await _get_or_create_tag(mock_db, "灵多", TAG_TYPE_SERIES)
        assert tag is existing
        assert created is False


class TestImportTaxonomy:
    @pytest.mark.anyio
    async def test_full_import(self):
        mock_db = AsyncMock()
        data = {
            "categories": {
                "坐具": {"name": "坐具", "children": ["办公椅", "访客椅"]},
                "办公桌": {"name": "办公桌", "children": ["升降桌"]},
            },
            "series": ["灵多", "灵多Pro"],
        }

        created_ids = []
        call_count = {"supplier": 0, "cat": 0, "tag": 0}

        async def fake_get_supplier(db):
            call_count["supplier"] += 1
            return MagicMock(id=MagicMock()), True

        async def fake_get_cat(db, name, parent_id, level):
            call_count["cat"] += 1
            cat = MagicMock(id=MagicMock(), category_name=name, level=level, parent_id=parent_id)
            created_ids.append(cat.id)
            return cat, True

        async def fake_get_tag(db, name, tag_type):
            call_count["tag"] += 1
            return MagicMock(id=MagicMock(), tag_name=name, tag_type=tag_type), True

        with (
            patch("app.scripts.import_sunon_taxonomy._get_or_create_supplier", fake_get_supplier),
            patch("app.scripts.import_sunon_taxonomy._get_or_create_category", fake_get_cat),
            patch("app.scripts.import_sunon_taxonomy._get_or_create_tag", fake_get_tag),
        ):
            counts = await import_taxonomy(mock_db, data)

        assert counts["supplier_created"] == 1
        assert counts["categories_l1_created"] == 2  # 坐具, 办公桌
        assert counts["categories_l2_created"] == 3  # 办公椅, 访客椅, 升降桌
        assert counts["tags_series_created"] == 2  # 灵多, 灵多Pro
        assert counts["categories_l1_existing"] == 0
        assert counts["categories_l2_existing"] == 0
        assert counts["tags_series_existing"] == 0

    @pytest.mark.anyio
    async def test_idempotent_rerun(self):
        """第二次运行: 所有记录已存在，created=0, existing=N."""
        mock_db = AsyncMock()
        data = {
            "categories": {
                "坐具": {"name": "坐具", "children": ["办公椅"]},
            },
            "series": ["灵多"],
        }

        async def fake_get_supplier(db):
            return MagicMock(), False

        async def fake_get_cat(db, name, parent_id, level):
            return MagicMock(), False

        async def fake_get_tag(db, name, tag_type):
            return MagicMock(), False

        with (
            patch("app.scripts.import_sunon_taxonomy._get_or_create_supplier", fake_get_supplier),
            patch("app.scripts.import_sunon_taxonomy._get_or_create_category", fake_get_cat),
            patch("app.scripts.import_sunon_taxonomy._get_or_create_tag", fake_get_tag),
        ):
            counts = await import_taxonomy(mock_db, data)

        assert counts["supplier_created"] == 0
        assert counts["categories_l1_created"] == 0
        assert counts["categories_l1_existing"] == 1
        assert counts["categories_l2_created"] == 0
        assert counts["categories_l2_existing"] == 1
        assert counts["tags_series_created"] == 0
        assert counts["tags_series_existing"] == 1

    @pytest.mark.anyio
    async def test_empty_taxonomy(self):
        mock_db = AsyncMock()
        data = {"categories": {}, "series": []}

        async def fake_get_supplier(db):
            return MagicMock(), False

        with patch("app.scripts.import_sunon_taxonomy._get_or_create_supplier", fake_get_supplier):
            counts = await import_taxonomy(mock_db, data)

        assert counts["categories_l1_created"] == 0
        assert counts["tags_series_created"] == 0
