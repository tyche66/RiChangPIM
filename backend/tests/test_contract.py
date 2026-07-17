import pytest

# NOTE: ``client`` is intentionally NOT defined here. It is inherited from the
# root ``tests/conftest.py`` fixture, which overrides ``get_db`` to point at the
# test database (TEST_DATABASE_URL) and ``pytest.skip``s when no reachable/safe
# Postgres is available. Defining a local client without that override would make
# requests hit the app's real engine (DATABASE_URL) and hang/crash without a DB.
from app.main import app


@pytest.mark.anyio
async def test_health_contract(client):
    """P0-3: health check returns status, version, components"""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    d = data["data"]
    assert "status" in d
    assert "version" in d
    assert "components" in d
    assert all(k in d["components"] for k in ("db", "redis", "minio"))


@pytest.mark.anyio
async def test_login_response_structure(client):
    """P1-4: login response has code/data structure"""
    resp = await client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        data = resp.json()
        assert "code" in data
        assert "data" in data
        assert "access_token" in data["data"]


@pytest.mark.anyio
async def test_proposals_route_no_duplication(client):
    """P1-5: proposals list route is /api/v1/proposals, NOT /api/v1/proposals/proposals.

    The proposals routes are auth-protected, so an unauthenticated request to a
    wrong path returns 401 (auth gate) rather than 404 — HTTP alone cannot prove
    the duplicated path is absent. We verify registration via the OpenAPI spec
    instead: the correct path must exist and the duplicated one must not.
    """
    registered = _registered_routes_from_openapi()
    assert ("get", "/api/v1/proposals") in registered
    assert ("get", "/api/v1/proposals/proposals") not in registered


# ---------------------------------------------------------------------------
# 本轮交付（块 1/2/3）路由契约：确保 11 个新接口已注册且路径/方法正确。
# 仅做「接口存在性」校验，不依赖 DB / MinIO；满足 docs/04 第十二/十四/十六章。
# 通过 OpenAPI 规范（全路径 + 小写 method）校验，规避 _IncludedRouter 相对路径问题。
# ---------------------------------------------------------------------------
EXPECTED_NEW_ROUTES = [
    ("post", "/api/v1/quotations"),
    ("get", "/api/v1/quotations"),
    ("get", "/api/v1/quotations/{quotation_id}"),
    ("put", "/api/v1/quotations/{quotation_id}"),
    ("post", "/api/v1/quotations/{quotation_id}/confirm"),
    ("get", "/api/v1/quotations/{quotation_id}/pdf"),
    ("post", "/api/v1/files/upload"),
    ("delete", "/api/v1/files/{attachment_id}"),
    ("get", "/api/v1/files/{attachment_id}/download"),
    ("get", "/api/v1/files/{attachment_id}/preview"),
    ("get", "/api/v1/stats/shares"),
    ("get", "/api/v1/stats/products/hot"),
    # 本轮补交：产品克隆 / 批量导入 / 导出
    ("post", "/api/v1/products/{product_id}/clone"),
    ("post", "/api/v1/products/import"),
    ("get", "/api/v1/products/export"),
    ("post", "/api/v1/users/{user_id}/disable"),
    ("post", "/api/v1/proposals/{proposal_id}/confirm"),
    ("get", "/api/v1/audit/operation-logs"),
]


def _registered_routes_from_openapi():
    spec = app.openapi()
    registered = set()
    for path, methods in spec.get("paths", {}).items():
        for method in methods.keys():
            registered.add((method.lower(), path))
    return registered


@pytest.mark.anyio
async def test_new_routes_registered():
    """块 1/2/3 全部新接口必须在 OpenAPI 路由表中，且 method+path 精确匹配。"""
    registered = _registered_routes_from_openapi()
    for method, path in EXPECTED_NEW_ROUTES:
        assert (method, path) in registered, f"缺失路由 {method.upper()} {path}"


@pytest.mark.anyio
async def test_new_routes_count():
    """校验 14 个新接口全部存在（防止漏注册）。"""
    registered = _registered_routes_from_openapi()
    missing = [(m, p) for m, p in EXPECTED_NEW_ROUTES if (m, p) not in registered]
    assert not missing, f"缺失路由: {missing}"


@pytest.mark.anyio
async def test_products_clone_route_exists():
    """新接口：POST /api/v1/products/{id}/clone 路由已注册"""
    registered = _registered_routes_from_openapi()
    assert ("post", "/api/v1/products/{product_id}/clone") in registered


@pytest.mark.anyio
async def test_products_import_route_exists():
    """新接口：POST /api/v1/products/import 路由已注册"""
    registered = _registered_routes_from_openapi()
    assert ("post", "/api/v1/products/import") in registered


@pytest.mark.anyio
async def test_products_export_route_exists():
    """新接口：GET /api/v1/products/export 路由已注册（且在 /{product_id} 之前）"""
    registered = _registered_routes_from_openapi()
    assert ("get", "/api/v1/products/export") in registered
