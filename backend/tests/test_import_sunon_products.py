import pytest

from app.scripts.import_sunon_products import validate_records


def _record():
    return {
        "product_no": "EMD89R.320190",
        "product_name": "总裁桌",
        "brand_name": "圣奥",
        "supplier_name": "圣奥",
        "category_parent": "办公桌",
        "category_name": "独立主管桌",
        "series": "铭达",
        "data_source": "source.txt",
        "face_price": 99999,
        "completeness_status": "pending",
    }


def test_validate_traceable_pending_product():
    assert validate_records([_record()])[0]["product_no"] == "EMD89R.320190"


def test_rejects_duplicate_product_number():
    with pytest.raises(ValueError, match="产品编号重复"):
        validate_records([_record(), _record()])


def test_placeholder_price_requires_pending_status():
    record = _record()
    record["completeness_status"] = "complete"
    with pytest.raises(ValueError, match="必须标记 pending"):
        validate_records([record])


def test_price_is_required():
    record = _record()
    del record["face_price"]
    with pytest.raises(ValueError, match="缺少字段: face_price"):
        validate_records([record])
