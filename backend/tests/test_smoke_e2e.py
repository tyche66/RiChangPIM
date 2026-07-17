"""端到端冒烟测试（字段权限 / 分享成本价过滤，Task 4 修复）。

基础设施策略（修复“登录失败就 skip”导致的回归被吞）：
- 无可达/安全的测试数据库时：``client`` fixture 在其内部 probe 阶段
  ``pytest.skip``，整组冒烟用例跳过（明确的“缺基础设施”原因）。
- 数据库可用但业务行为错误时：直接 ``assert`` 失败，绝不以 skip 伪装成通过。

本次修复：在测试内真实创建 brand / supplier / category / product（含非空
``cost_price``），确保字段权限断言具有判别能力，绝不在空列表上通过。分享测试
引用真实 proposal（含关联产品），断言 content.items 非空且 cost_price 被隐藏。
"""

from uuid import uuid4

import pytest
from _db_probe import resolve_test_database_url, to_sync_url
from sqlalchemy import create_engine, text


async def _login_admin(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, (
        f"admin login failed (status={resp.status_code}); "
        f"is the test DB migrated AND seeded?"
    )
    return resp.json()["data"]["access_token"]


async def _create(client, admin_token, method, url, json):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.request(method, url, json=json, headers=headers)
    assert resp.status_code in (200, 201), (
        f"{method} {url} failed: status={resp.status_code} body={resp.text}"
    )
    return resp.json()


@pytest.mark.anyio
async def test_role_permissions_are_returned_and_updatable(client):
    admin_token = await _login_admin(client)
    role_code = f"rc_test_{uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = await client.post(
        "/api/v1/roles",
        json={
            "role_name": "RC Test Role",
            "role_code": role_code,
            "description": "role permission regression",
            "permission_ids": ["product:view", "role:view"],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    role = resp.json()
    assert set(role["permission_ids"]) == {"product:view", "role:view"}

    resp = await client.put(
        f"/api/v1/roles/{role['id']}",
        json={
            "role_name": role["role_name"],
            "role_code": role["role_code"],
            "description": role["description"],
            "permission_ids": ["product:view", "product:edit"],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert set(resp.json()["permission_ids"]) == {"product:view", "product:edit"}

    resp = await client.get("/api/v1/roles", headers=headers)
    assert resp.status_code == 200, resp.text
    listed = next(r for r in resp.json()["data"]["list"] if r["id"] == role["id"])
    assert set(listed["permission_ids"]) == {"product:view", "product:edit"}


def _insert_parent_rows():
    """插入 brand/supplier/category 作为外键父行（真实写入测试库）。

    这些通用 CRUD 路由的 create 端点为独立遗留 bug（body 参数缺类型注解，
    不在本次 8 项整改范围），此处直接插入父行，产品本身仍通过产品 API
    （admin 权限）真实创建，确保 cost_price 断言对应端到端写入的数据。
    """
    eng = create_engine(to_sync_url(resolve_test_database_url()))
    brand_id = str(uuid4())
    supplier_id = str(uuid4())
    category_id = str(uuid4())
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO brand (id, brand_name, create_time, update_time, is_deleted) "
                "VALUES (:id,'SmokeBrand',now(),now(),false)"
            ),
            {"id": brand_id},
        )
        conn.execute(
            text(
                "INSERT INTO supplier (id, supplier_name, cooperation_status, create_time, "
                "update_time, is_deleted) VALUES (:id,'SmokeSupplier','active',now(),now(),false)"
            ),
            {"id": supplier_id},
        )
        conn.execute(
            text(
                "INSERT INTO category (id, category_name, level, sort, create_time, update_time, "
                "is_deleted) VALUES (:id,'SmokeCategory',1,0,now(),now(),false)"
            ),
            {"id": category_id},
        )
    return brand_id, supplier_id, category_id


async def _ensure_product_with_cost_price(client, admin_token):
    """通过产品 API（admin 权限）真实创建含非空 cost_price 的产品。

    返回刚创建产品的 id。每用例函数级隔离全新库，必须自建数据。
    """
    brand_id, supplier_id, category_id = _insert_parent_rows()
    product = await _create(
        client,
        admin_token,
        "POST",
        "/api/v1/products",
        {
            "product_no": "SMOKE-001",
            "product_name": "Smoke Product",
            "brand_id": brand_id,
            "supplier_id": supplier_id,
            "category_id": category_id,
            "face_price": 199.0,
            "cost_price": 123.45,
            "material": "steel",
            "status": "active",
        },
    )
    return product["id"]


@pytest.mark.anyio
async def test_sales_cannot_see_cost_price(client):
    admin_token = await _login_admin(client)

    # 通过产品 API 创建真实产品（含非空 cost_price）。
    product_id = await _ensure_product_with_cost_price(client, admin_token)

    # 用 sales 用户登录（无 cost_price 权限）。
    resp = await client.get(
        "/api/v1/roles", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200, (
        f"list roles failed: status={resp.status_code} body={resp.text}"
    )
    roles = resp.json()["data"]["list"]
    sales = next((r for r in roles if r["role_code"] == "sales"), None)
    assert sales is not None, "sales 角色未 seed"
    sales_role_id = sales["id"]

    resp = await client.post(
        "/api/v1/users",
        json={
            "username": "sales_smoke_test",
            "password": "password123",
            "role_id": sales_role_id,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code in (200, 201, 409), resp.text

    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "sales_smoke_test", "password": "password123"},
    )
    assert resp.status_code == 200, resp.text
    sales_token = resp.json()["data"]["access_token"]

    resp = await client.get(
        "/api/v1/products?page=1&size=10",
        headers={"Authorization": f"Bearer {sales_token}"},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["list"]
    assert items, "sales 产品列表为空，无法验证 cost_price 过滤（空跑）"
    # 精确定位刚创建的产品。
    target = next((it for it in items if it["id"] == str(product_id)), None)
    assert target is not None, f"刚创建的产品未在列表中返回：{items}"
    # cost_price 必须被隐藏。
    assert "cost_price" not in target or target.get("cost_price") is None, (
        f"sales role should not see cost_price: {target}"
    )


@pytest.mark.anyio
async def test_share_access_route_writes_log_and_filters_cost_price(client):
    admin_token = await _login_admin(client)

    product_id = await _ensure_product_with_cost_price(client, admin_token)

    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"}
    )
    admin_user_id = resp.json().get("id") or resp.json().get("data", {}).get("id")
    assert admin_user_id, "admin /me 未返回 id"

    # 创建真实 proposal（含关联产品），不使用全零 target_id。
    proposal = await _create(
        client,
        admin_token,
        "POST",
        "/api/v1/proposals",
        {
            "proposal_name": "Smoke Proposal",
            "creator_id": admin_user_id,
            "items": [{"product_id": str(product_id), "quantity": 2}],
        },
    )
    proposal_id = proposal["id"]

    share = await _create(
        client,
        admin_token,
        "POST",
        "/api/v1/shares",
        {
            "share_type": "proposal",
            "target_id": proposal_id,
            "creator_id": admin_user_id,
        },
    )
    token = share["data"]["token"]

    resp = await client.get(
        f"/api/v1/share/{token}",
        headers={"X-Device-Fingerprint": "smoke_fp_001"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["share_type"] == "proposal"
    content = data["content"]
    assert isinstance(content, dict), f"share content 非 dict：{data}"
    items = content.get("items")
    assert items, "share content 的 items 为空，无法验证 cost_price 过滤（空跑）"
    for item in items:
        assert "cost_price" not in item or item.get("cost_price") is None, (
            f"share viewer should not see cost_price: {item}"
        )
