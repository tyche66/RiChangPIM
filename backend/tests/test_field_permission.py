import pytest

pytestmark = pytest.mark.anyio


def test_sales_role_hides_cost_price():
    from app.core.serializers import filter_sensitive_fields

    payload = {"id": "abc", "product_name": "X", "cost_price": 99.0, "supplier_id": "sup-1"}
    out = filter_sensitive_fields(payload, role_code="sales")
    assert "cost_price" not in out
    assert "supplier_id" not in out
    assert out["product_name"] == "X"


def test_admin_role_sees_all_fields():
    from app.core.serializers import filter_sensitive_fields

    payload = {"id": "abc", "cost_price": 99.0, "supplier_id": "sup-1"}
    out = filter_sensitive_fields(payload, role_code="admin")
    assert out["cost_price"] == 99.0
    assert out["supplier_id"] == "sup-1"


def test_finance_role_sees_all_fields():
    from app.core.serializers import filter_sensitive_fields

    payload = {"cost_price": 99.0}
    out = filter_sensitive_fields(payload, role_code="finance")
    assert out["cost_price"] == 99.0


def test_product_manager_role_sees_all_fields():
    from app.core.serializers import filter_sensitive_fields

    payload = {"cost_price": 99.0, "supplier_id": "x"}
    out = filter_sensitive_fields(payload, role_code="product_manager")
    assert out["cost_price"] == 99.0
    assert out["supplier_id"] == "x"


def test_viewer_role_hides_sensitive():
    from app.core.serializers import filter_sensitive_fields

    payload = {"cost_price": 50.0, "supplier_id": "s"}
    out = filter_sensitive_fields(payload, role_code="viewer")
    assert "cost_price" not in out
    assert "supplier_id" not in out


def test_unknown_role_falls_back_to_hiding():
    from app.core.serializers import filter_sensitive_fields

    payload = {"cost_price": 1.0}
    out = filter_sensitive_fields(payload, role_code="intern")
    assert "cost_price" not in out


def test_list_payload_filter_recursively():
    from app.core.serializers import filter_sensitive_fields

    payload = [{"cost_price": 1.0, "name": "a"}, {"cost_price": 2.0, "name": "b"}]
    out = filter_sensitive_fields(payload, role_code="sales")
    assert "cost_price" not in out[0]
    assert out[0]["name"] == "a"
    assert "cost_price" not in out[1]
    assert out[1]["name"] == "b"


def test_no_role_fails_closed_by_default():
    from app.core.serializers import filter_sensitive_fields

    payload = {"cost_price": 1.0}
    out = filter_sensitive_fields(payload, role_code=None)
    assert "cost_price" not in out
