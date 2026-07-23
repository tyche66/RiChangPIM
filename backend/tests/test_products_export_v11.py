from io import BytesIO

import pandas as pd

from app.services.products_export import _build_query, build_excel_bytes


def test_price_filter_excludes_placeholder_price():
    sql = str(_build_query(min_price=100).compile(compile_kwargs={"literal_binds": True}))
    assert "product.face_price != 99999" in sql


def test_tag_filter_uses_product_tag_relationship():
    sql = str(
        _build_query(tag_ids="00000000-0000-0000-0000-000000000001").compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "product_tag.product_id" in sql
    assert "product_tag.tag_id" in sql


def test_sales_export_hides_sensitive_columns_and_placeholder_value():
    content = build_excel_bytes(
        [
            {
                "product_id": "1",
                "product_no": "P-1",
                "product_name": "Product",
                "brand_name": "Brand",
                "supplier_name": "Supplier",
                "category_name": "Category",
                "face_price": "待核价",
                "cost_price": 1,
                "material": None,
                "stock_status": "unknown",
                "status": "draft",
                "description": None,
                "specification": None,
                "colors": None,
                "data_source": "source.pdf",
                "completeness_status": "pending",
                "create_time": "",
                "update_time": "",
                "tags": "Series",
            }
        ],
        role_code="sales",
    )
    frame = pd.read_excel(BytesIO(content))
    assert "cost_price" not in frame.columns
    assert "supplier_name" not in frame.columns
    assert frame.loc[0, "面价"] == "待核价"
