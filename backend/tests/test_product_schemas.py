from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.product import ProductResponse, ProductUpdate


def test_product_response_serializes_orm_tags():
    product = {
        "id": uuid4(),
        "product_no": "P-1",
        "product_name": "Product",
        "brand_id": uuid4(),
        "supplier_id": uuid4(),
        "category_id": uuid4(),
        "face_price": 99999,
        "completeness_status": "pending",
        "create_time": "2026-07-17T00:00:00Z",
        "update_time": "2026-07-17T00:00:00Z",
        "tags": [SimpleNamespace(tag_name="铭达")],
    }
    assert ProductResponse.model_validate(product).tags == ["铭达"]


def test_product_update_rejects_null_face_price():
    with pytest.raises(ValidationError, match="面价不可为空"):
        ProductUpdate(face_price=None)
