"""RBAC 权限契约测试 + 附件 file_type 映射测试（安全整改回归防护）。

覆盖：
- 每条阶段①②③新增非公开接口都挂载了「正确权限码」的 PermissionChecker（静态自省，无需 DB）。
- 路由引用的权限码必须是 seed_data.PERMISSIONS 与 0004 迁移 PERMISSIONS 的子集。
- 缺 Token -> 401；缺权限 -> 403（PermissionChecker 在业务/审计之前抛出，无需 DB）。
- 有权限可进入业务（需要 DB，无 DB 时 skip）。
- 公开 share 接口不挂 PermissionChecker（无需 JWT，静态自省 + 可选 HTTP）。

设计要点：401/403 用例在权限校验阶段即抛出，不会触达 get_db 的实际查询或 audit
落库，因此无需数据库即可运行；仅「有权限进入业务」「公开 share 命中业务」这两类
需要真实 DB，按 test_seed_data.py 的既有约定用 skipif 优雅跳过。
"""

import importlib.util
import pathlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.audit import router as audit_router
from app.api.v1.files import router as files_router
from app.api.v1.products import router as products_router
from app.api.v1.proposals import router as proposals_router
from app.api.v1.quotations import router as quotations_router
from app.api.v1.share_token import router as share_token_router
from app.api.v1.stats import router as stats_router
from app.api.v1.users import router as users_router
from app.core.permission import PermissionChecker
from app.core.security import create_access_token
from app.scripts.seed_data import PERMISSIONS as SEED_PERMISSIONS

# ---------------------------------------------------------------------------
# 期望的「路由 -> 权限码」映射（与整改需求一一对应）。
# ---------------------------------------------------------------------------
EXPECTED_ROUTE_PERMISSIONS = {
    ("GET", "/api/v1/quotations"): "quotation:view",
    ("GET", "/api/v1/quotations/{quotation_id}"): "quotation:view",
    ("GET", "/api/v1/quotations/{quotation_id}/pdf"): "quotation:view",
    ("POST", "/api/v1/quotations"): "quotation:create",
    ("PUT", "/api/v1/quotations/{quotation_id}"): "quotation:edit",
    ("POST", "/api/v1/quotations/{quotation_id}/confirm"): "quotation:confirm",
    ("POST", "/api/v1/files/upload"): "file:upload",
    ("DELETE", "/api/v1/files/{attachment_id}"): "file:delete",
    ("GET", "/api/v1/files/{attachment_id}/download"): "file:view",
    ("GET", "/api/v1/files/{attachment_id}/preview"): "file:view",
    ("GET", "/api/v1/stats/shares"): "stats:view",
    ("GET", "/api/v1/stats/products/hot"): "stats:view",
    ("POST", "/api/v1/products/{product_id}/clone"): "product:clone",
    ("POST", "/api/v1/products/import"): "product:import",
    ("GET", "/api/v1/products/export"): "product:export",
    ("POST", "/api/v1/users/{user_id}/disable"): "user:disable",
    ("POST", "/api/v1/proposals/{proposal_id}/confirm"): "proposal:confirm",
    ("GET", "/api/v1/audit/operation-logs"): "audit:view",
}

_ROUTER_PREFIX = [
    (quotations_router, "/api/v1/quotations"),
    (files_router, "/api/v1/files"),
    (stats_router, "/api/v1/stats"),
    (products_router, "/api/v1/products"),
    (users_router, "/api/v1/users"),
    (proposals_router, "/api/v1/proposals"),
    (audit_router, "/api/v1/audit"),
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
    """自省所有目标路由，返回 {(METHOD, full_path): [perm, ...]}。"""
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
    """从 seed migration 和后续权限 migration 加载 PERMISSIONS。"""
    versions_dir = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"
    permissions = []
    for filename in ("0004_seed_data.py", "0008_v11_audit_workflow_ocr.py"):
        path = versions_dir / filename
        spec = importlib.util.spec_from_file_location(f"_mig_{filename}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        permissions.extend(getattr(mod, "PERMISSIONS", []))
    return permissions


# ---------------------------------------------------------------------------
# 静态契约（无需 DB）
# ---------------------------------------------------------------------------
def test_each_route_has_expected_permission_checker():
    """每条受保护路由必须挂载「正确权限码」的 PermissionChecker。"""
    actual = _actual_route_permissions()
    for key, expected_perm in EXPECTED_ROUTE_PERMISSIONS.items():
        assert key in actual, f"缺失路由: {key}"
        assert actual[key] == [expected_perm], (
            f"路由 {key} 权限码不符：期望 [{expected_perm}]，实际 {actual[key]}"
        )


def test_public_share_route_has_no_permission_checker():
    """公开接口 GET /api/v1/share/{token} 不得挂载 PermissionChecker（无需后台 JWT）。"""
    actual = _actual_route_permissions()
    key = ("GET", "/api/v1/share/{token}")
    assert key in actual, "share 路由缺失"
    assert actual[key] == [], "公开 share 接口不应要求后台权限"


def test_route_permissions_are_subset_of_seed_permissions():
    """自动化断言：新增路由引用的权限码 ⊆ seed_data.PERMISSIONS。"""
    seed_codes = {p[0] for p in SEED_PERMISSIONS}
    used = set(EXPECTED_ROUTE_PERMISSIONS.values())
    # 同时校验实际自省到的权限码，防止代码与期望表脱节
    for perms in _actual_route_permissions().values():
        used.update(perms)
    missing = used - seed_codes
    assert not missing, f"以下权限码不在 seed_data.PERMISSIONS 中: {missing}"


def test_route_permissions_are_subset_of_migration_permissions():
    """自动化断言：新增路由引用的权限码 ⊆ 0004 迁移 PERMISSIONS。"""
    mig_codes = {p[0] for p in _migration_permissions()}
    used = set(EXPECTED_ROUTE_PERMISSIONS.values())
    missing = used - mig_codes
    assert not missing, f"以下权限码不在 0004_seed_data 迁移 PERMISSIONS 中: {missing}"


def test_products_export_registered_before_dynamic_id():
    """静态路径 /export 必须在 /{product_id} 之前注册，避免被动态段抢占。"""
    paths = [r.path for r in products_router.routes]
    assert "/export" in paths and "/{product_id}" in paths
    assert paths.index("/export") < paths.index("/{product_id}")


# ---------------------------------------------------------------------------
# HTTP 契约：缺 Token 401 / 缺权限 403（无需 DB）
# ---------------------------------------------------------------------------
@pytest.fixture
async def noauth_client():
    """轻量 ASGI client，不覆盖 get_db；仅用于权限校验前即返回的用例。"""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _token(perms):
    return create_access_token(
        {"sub": "00000000-0000-0000-0000-000000000000", "role_code": "tester", "perms": perms}
    )


@pytest.mark.anyio
async def test_missing_token_returns_401(noauth_client):
    resp = await noauth_client.get("/api/v1/quotations")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == 40101


@pytest.mark.anyio
async def test_wrong_permission_returns_403(noauth_client):
    token = _token(["some:other"])  # 有合法 token 但无 quotation:view
    resp = await noauth_client.get(
        "/api/v1/quotations", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == 40301


@pytest.mark.anyio
async def test_missing_token_401_across_protected_routes(noauth_client):
    """一批受保护 GET 路由在缺 Token 时统一 401（权限层先于业务/审计触发）。"""
    for path in (
        "/api/v1/quotations",
        "/api/v1/stats/shares",
        "/api/v1/stats/products/hot",
        "/api/v1/products/export",
    ):
        resp = await noauth_client.get(path)
        assert resp.status_code == 401, f"{path} 缺 Token 应为 401"


# ---------------------------------------------------------------------------
# 需要真实 DB 的用例：有权限进入业务 / 公开 share 命中业务（无 DB 时 skip）。
# 不再在模块导入期连接数据库（保持 ``--collect-only`` 零连接）；改由根
# conftest 的 ``client`` fixture 在 fixture 阶段做轻量可达性探测并 pytest.skip。
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_valid_permission_enters_business(client):
    """有 quotation:view 权限时可进入业务逻辑（返回 200 分页结构，非 401/403）。"""
    token = _token(["quotation:view"])
    resp = await client.get("/api/v1/quotations", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert "list" in body["data"]


@pytest.mark.anyio
async def test_public_share_does_not_require_jwt(client):
    """公开 share 接口无 JWT 也能进入业务逻辑（未知 token -> 404，而非 401）。"""
    resp = await client.get("/api/v1/share/nonexistent_token_rbac_test")
    assert resp.status_code != 401
    assert resp.status_code == 404
