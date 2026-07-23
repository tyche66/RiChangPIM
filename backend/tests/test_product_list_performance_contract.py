from pathlib import Path


def test_product_list_uses_joined_load_for_single_parent_relations():
    source = (
        Path(__file__).parents[1] / "app" / "api" / "v1" / "products.py"
    ).read_text(encoding="utf-8")

    assert "joinedload(Product.brand)" in source
    assert "joinedload(Product.supplier)" in source
    assert "joinedload(Product.category)" in source
    assert "selectinload(Product.tags)" in source
    assert "selectinload(Product.images).joinedload(ProductImage.attachment)" in source
    assert "items = [_product_list_response(p, request) for p in products]" in source


def test_container_avoids_duplicate_uvicorn_access_logs():
    entrypoint = (
        Path(__file__).parents[1] / "docker" / "backend-entrypoint.sh"
    ).read_text(encoding="utf-8")
    assert "--no-access-log" in entrypoint
    assert '--workers "${UVICORN_WORKERS:-2}"' in entrypoint
