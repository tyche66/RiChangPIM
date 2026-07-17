"""旧模块 RBAC 整改契约测试（安全回归防护）。

覆盖报告中 P0 阻塞的原有模块：users / roles / products / categories / brands /
suppliers / tags / proposals / shares / ai。

- 静态自省：每条敏感路由都挂载了「正确权限码」的 PermissionChecker，且引用
  的权限码 ⊆ seed_data.PERMISSIONS（与 0004 迁移一致）。
- 公开接口 GET /api/v1/share/{token} 不得挂载 PermissionChecker。
- HTTP 契约（无需 DB）：
  * 缺 Token -> 401；有合法 Token 但无对应权限 -> 403；
  * 权限校验在业务/审计落库之前抛出，故不触发 DB 写入。
- 有权限进入业务（需要 DB，无 DB 时 skip）。

权限码映射与 docs/04 + 49 项权限目录（0004 迁移）一一对应。
"""

import importlib.util
import pathlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.ai import router as ai_router
from app.api.v1.brands import router as brands_router
from app.api.v1.categories import router as categories_router
from app.api.v1.products import router as products_router
from app.api.v1.proposals import router as proposals_router
from app.api.v1.roles import router as roles_router
from app.api.v1.share_token import router as share_token_router
from app.api.v1.shares import router as shares_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.tags import router as tags_router
from app.api.v1.users import router as users_router
from app.core.permission import PermissionChecker
from app.core.security import create_access_token
from app.scripts.seed_data import PERMISSIONS as SEED_PERMISSIONS

# (METHOD, full_path) -> 期望权限码（None 表示该路由为公开接口，不应要求权限）
EXPECTED_OLD_ROUTE_PERMISSIONS = {
    # users
    ("GET", "/api/v1/users"): "user:view",
    ("GET", "/api/v1/users/{user_id}"): "user:view",
    ("POST", "/api/v1/users"): "user:create",
    ("PUT", "/api/v1/users/{user_id}"): "user:edit",
    ("DELETE", "/api/v1/users/{user_id}"): "user:delete",
    # roles
    ("GET", "/api/v1/roles"): "role:view",
    ("POST", "/api/v1/roles"): "role:create",
    ("PUT", "/api/v1/roles/{role_id}"): "role:edit",
    ("DELETE", "/api/v1/roles/{role_id}"): "role:delete",
    # products（export/clone/import 已在 test_permission_contract 覆盖）
    ("GET", "/api/v1/products"): "product:view",
    ("GET", "/api/v1/products/{product_id}"): "product:view",
    ("POST", "/api/v1/products"): "product:create",
    ("PUT", "/api/v1/products/{product_id}"): "product:edit",
    ("DELETE", "/api/v1/products/{product_id}"): "product:delete",
    ("PATCH", "/api/v1/products/{product_id}/status"): "product:status",
    # categories
    ("GET", "/api/v1/categories"): "category:view",
    ("POST", "/api/v1/categories"): "category:create",
    ("PUT", "/api/v1/categories/{category_id}"): "category:edit",
    ("DELETE", "/api/v1/categories/{category_id}"): "category:delete",
    # brands
    ("GET", "/api/v1/brands"): "brand:view",
    ("POST", "/api/v1/brands"): "brand:create",
    ("PUT", "/api/v1/brands/{item_id}"): "brand:edit",
    ("DELETE", "/api/v1/brands/{item_id}"): "brand:delete",
    # suppliers
    ("GET", "/api/v1/suppliers"): "supplier:view",
    ("POST", "/api/v1/suppliers"): "supplier:create",
    ("PUT", "/api/v1/suppliers/{item_id}"): "supplier:edit",
    ("DELETE", "/api/v1/suppliers/{item_id}"): "supplier:delete",
    # tags
    ("GET", "/api/v1/tags"): "tag:view",
    ("POST", "/api/v1/tags"): "tag:create",
    ("PUT", "/api/v1/tags/{item_id}"): "tag:edit",
    ("DELETE", "/api/v1/tags/{item_id}"): "tag:delete",
    # proposals
    ("GET", "/api/v1/proposals"): "proposal:view",
    ("GET", "/api/v1/proposals/{proposal_id}"): "proposal:view",
    ("POST", "/api/v1/proposals"): "proposal:create",
    ("PUT", "/api/v1/proposals/{proposal_id}"): "proposal:edit",
    ("DELETE", "/api/v1/proposals/{proposal_id}"): "proposal:delete",
    # shares（后台管理接口；公开 GET /share/{token} 单独豁免）
    ("POST", "/api/v1/shares"): "share:create",
    ("GET", "/api/v1/shares"): "share:view",
    ("DELETE", "/api/v1/shares/{share_id}"): "share:delete",
    # ai（embeddings / rag/index 另需 admin 角色，权限码仍为 ai:use）
    ("POST", "/api/v1/ai/chat"): "ai:use",
    ("POST", "/api/v1/ai/embeddings"): "ai:use",
    ("POST", "/api/v1/ai/rag/search"): "ai:use",
    ("POST", "/api/v1/ai/rag/index"): "ai:use",
    ("POST", "/api/v1/ai/proposal/{proposal_id}/polish"): "ai:use",
    ("POST", "/api/v1/ai/recommend"): "ai:use",
    # 公开接口（豁免后台 JWT / RBAC）
    ("GET", "/api/v1/share/{token}"): None,
}

_ROUTER_PREFIX = [
    (users_router, "/api/v1/users"),
    (roles_router, "/api/v1/roles"),
    (products_router, "/api/v1/products"),
    (categories_router, "/api/v1/categories"),
    (brands_router, "/api/v1/brands"),
    (suppliers_router, "/api/v1/suppliers"),
    (tags_router, "/api/v1/tags"),
    (proposals_router, "/api/v1/proposals"),
    (shares_router, "/api/v1/shares"),
    (ai_router, "/api/v1/ai"),
    (share_token_router, "/api/v1"),
]


def _collect_permissions(dependant, out):
    if dependant is None:
        return
    call = getattr(dependant, "call", None)
    if isinstance(call, PermissionChecker):
        out.append(call.required_permission)
    for sub in getattr(dependant, "dependencies", []):
        _collect_permissions(sub, out)


def _actual_route_permissions():
    result = {}
    for router, prefix in _ROUTER_PREFIX:
        for route in router.routes:
            perms = []
            _collect_permissions(getattr(route, "dependant", None), perms)
            for method in getattr(route, "methods", None) or []:
                if method == "HEAD":
                    continue
                result[(method, f"{prefix}{route.path}")] = sorted(set(perms))
    return result


def _migration_permissions():
    versions_dir = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"
    permissions = []
    for filename in ("0004_seed_data.py", "0008_v11_audit_workflow_ocr.py"):
        path = versions_dir / filename
        spec = importlib.util.spec_from_file_location(f"_mig_{filename}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        permissions.extend(getattr(mod, "PERMISSIONS", []))
    return permissions


def test_each_old_route_has_expected_permission_checker():
    """每条旧模块敏感路由必须挂载「正确权限码」的 PermissionChecker。"""
    actual = _actual_route_permissions()
    for key, expected_perm in EXPECTED_OLD_ROUTE_PERMISSIONS.items():
        assert key in actual, f"缺失路由: {key}"
        if expected_perm is None:
            # 公开接口：不要求任何后台权限码
            assert actual[key] == [], f"公开接口 {key} 不应要求后台权限，实际 {actual[key]}"
        else:
            assert actual[key] == [expected_perm], (
                f"路由 {key} 权限码不符：期望 [{expected_perm}]，实际 {actual[key]}"
            )


def test_old_route_permissions_are_subset_of_seed_permissions():
    """旧模块路由引用的权限码 ⊆ seed_data.PERMISSIONS。"""
    seed_codes = {p[0] for p in SEED_PERMISSIONS}
    used = set(EXPECTED_OLD_ROUTE_PERMISSIONS.values()) - {None}
    for perms in _actual_route_permissions().values():
        used.update(perms)
    missing = used - seed_codes
    assert not missing, f"以下权限码不在 seed_data.PERMISSIONS 中: {missing}"


def test_old_route_permissions_are_subset_of_migration_permissions():
    """旧模块路由引用的权限码 ⊆ 权限种子 migration 集合。"""
    mig_codes = {p[0] for p in _migration_permissions()}
    used = set(EXPECTED_OLD_ROUTE_PERMISSIONS.values()) - {None}
    for perms in _actual_route_permissions().values():
        used.update(perms)
    missing = used - mig_codes
    assert not missing, f"以下权限码不在权限迁移 PERMISSIONS 中: {missing}"


def _token(perms, role_code="tester"):
    return create_access_token(
        {"sub": "00000000-0000-0000-0000-000000000000", "role_code": role_code, "perms": perms}
    )


# GET 敏感路由（均无 @audit_action；缺 Token/缺权限时权限层先于审计落库抛出，无需 DB）
_OLD_GET_ROUTES = [
    "/api/v1/users",
    "/api/v1/roles",
    "/api/v1/products",
    "/api/v1/categories",
    "/api/v1/brands",
    "/api/v1/suppliers",
    "/api/v1/tags",
    "/api/v1/proposals",
    "/api/v1/shares",
]


@pytest.fixture
async def noauth_client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_old_protected_routes_missing_token_returns_401(noauth_client):
    """旧模块敏感 GET 路由缺 Token 统一返回 401。"""
    for path in _OLD_GET_ROUTES:
        resp = await noauth_client.get(path)
        assert resp.status_code == 401, (
            f"{path} 缺 Token 应为 401，实际 {resp.status_code}"
        )


@pytest.mark.anyio
async def test_old_protected_routes_wrong_permission_returns_403(noauth_client):
    """有合法 Token 但无对应权限 -> 403。"""
    token = _token(["some:other"])
    for path in _OLD_GET_ROUTES:
        resp = await noauth_client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, (
            f"{path} 缺权限应为 403，实际 {resp.status_code}"
        )
        assert resp.json()["detail"]["code"] == 40301


@pytest.mark.anyio
async def test_ai_routes_require_ai_use_permission(noauth_client):
    """AI 路由需 ai:use；无此权限 -> 403（chat/recommend/rag-search 无审计落库）。"""
    token = _token(["some:other"])
    bodies = {
        "/api/v1/ai/chat": {"message": "hi"},
        "/api/v1/ai/recommend": {"requirement": "x"},
        "/api/v1/ai/rag/search": {"query": "x"},
    }
    for path, body in bodies.items():
        resp = await noauth_client.post(
            path, json=body, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403, (
            f"{path} 缺 ai:use 应为 403，实际 {resp.status_code}"
        )


@pytest.mark.anyio
async def test_ai_admin_routes_require_admin_role(noauth_client):
    """embeddings / rag/index 需 ai:use + admin 角色；非 admin 持 ai:use -> 403。"""
    token = _token(["ai:use"], role_code="sales")
    bodies = {
        "/api/v1/ai/embeddings": {"texts": ["x"]},
        "/api/v1/ai/rag/index": {
            "product_manual_id": "00000000-0000-0000-0000-000000000000"
        },
    }
    for path, body in bodies.items():
        resp = await noauth_client.post(
            path, json=body, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403, (
            f"{path} 非 admin 应为 403，实际 {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 需要真实 DB 的用例：有权限进入业务（无 DB 时由根 conftest 的 client skip）。
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_user_view_authorized_enters_business(client):
    """有 user:view 权限时可进入用户列表业务逻辑（返回 200，非 401/403）。"""
    token = _token(["user:view"], role_code="admin")
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


@pytest.mark.anyio
async def test_role_view_authorized_enters_business(client):
    """有 role:view 权限时可进入角色列表业务逻辑。"""
    token = _token(["role:view"], role_code="admin")
    resp = await client.get("/api/v1/roles", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


@pytest.mark.anyio
async def test_product_view_authorized_enters_business(client):
    """有 product:view 权限（如 sales）时可进入产品列表业务逻辑。"""
    token = _token(["product:view"], role_code="sales")
    resp = await client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "list" in resp.json()["data"]
