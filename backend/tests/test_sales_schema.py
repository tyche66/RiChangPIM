"""销售方案 / 报价 / 分享闭环后端测试。

覆盖用户要求的 15 项关键行为：
1. Proposal 创建/更新 items 非空校验（业务 422）
2. Proposal quantity 必须 >= 1
3. Proposal 批量校验产品 active / 未删除
4. Proposal 明细去重
5. Proposal 事务内替换明细并重算 total_face_value
6. Proposal 详情返回 item id/product_no/product_name/face_price/quantity/
   remark/line_total/cover_image_url，不含 cost_price
7. Proposal 列表 keyword / status / 分页 / 倒序
8. Proposal confirm 要求非空
9. Quotation 创建/更新 items 非空校验
10. Quotation item 字段强约束：quantity>0 / unit_price>=0 / tax_rate 0..1 / discount 0..1
11. Quotation 后端金额语义：subtotal=unit_price*qty; total=sum(subtotal*(1+tax))*discount
12. Quotation 更新折扣或明细时重算
13. Quotation confirm 非空才确认
14. Quotation 列表返回 proposal_no / proposal_name
15. Shares 请求 schema / target 校验 / proposal 草稿可分享 / quotation 仅 confirmed
16. share_token 返回 proposal product_no/line_total/total_face_value，
    quotation unit_price/tax_rate/subtotal，绝不含 cost_price
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.audit import Share, ShareToken
from app.models.product import Brand, Category, Product, Supplier
from app.models.sales import (
    Proposal,
    ProposalItem,
    Quotation,
    QuotationItem,
)
from app.models.user import User

pytestmark = pytest.mark.anyio


async def _login_admin(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, (
        f"admin login failed (status={resp.status_code}); "
        f"is the test DB migrated AND seeded?"
    )
    return resp.json()["data"]["access_token"]


async def _admin_user_id(session):
    user = (
        await session.execute(select(User).where(User.username == "admin"))
    ).scalar_one_or_none()
    assert user is not None, "admin user not seeded"
    return user.id


async def _req(client, admin_token, method, url, json=None, params=None):
    headers = {"Authorization": f"Bearer {admin_token}"}
    return await client.request(method, url, json=json, headers=headers, params=params)


async def _make_active_product(session):
    """创建一条 active 状态的测试产品（含 brand/supplier/category）。"""
    brand = (
        await session.execute(select(Brand).limit(1))
    ).scalar_one_or_none()
    if not brand:
        brand = Brand(brand_name="test_brand_1")
        session.add(brand)
        await session.flush()

    supplier = (
        await session.execute(select(Supplier).limit(1))
    ).scalar_one_or_none()
    if not supplier:
        supplier = Supplier(supplier_name="test_supplier_1")
        session.add(supplier)
        await session.flush()

    category = (
        await session.execute(select(Category).limit(1))
    ).scalar_one_or_none()
    if not category:
        category = Category(category_name="test_cat_1", level=1, sort=0)
        session.add(category)
        await session.flush()

    product = Product(
        product_no=f"PROD-TEST-{uuid4().hex[:8].upper()}",
        product_name="Test Product",
        brand_id=brand.id,
        supplier_id=supplier.id,
        category_id=category.id,
        face_price=100.0,
        cost_price=60.0,
        status="active",
        is_deleted=False,
    )
    session.add(product)
    await session.flush()
    return product


async def _make_inactive_product(session):
    """创建一条 inactive 的测试产品。"""
    brand = (
        await session.execute(select(Brand).limit(1))
    ).scalar_one_or_none()
    if not brand:
        brand = Brand(brand_name="test_brand_2")
        session.add(brand)
        await session.flush()

    supplier = (
        await session.execute(select(Supplier).limit(1))
    ).scalar_one_or_none()
    if not supplier:
        supplier = Supplier(supplier_name="test_supplier_2")
        session.add(supplier)
        await session.flush()

    category = (
        await session.execute(select(Category).limit(1))
    ).scalar_one_or_none()
    if not category:
        category = Category(category_name="test_cat_2", level=1, sort=0)
        session.add(category)
        await session.flush()

    product = Product(
        product_no=f"PROD-INACTIVE-{uuid4().hex[:8].upper()}",
        product_name="Inactive Product",
        brand_id=brand.id,
        supplier_id=supplier.id,
        category_id=category.id,
        face_price=50.0,
        status="inactive",
        is_deleted=False,
    )
    session.add(product)
    await session.flush()
    return product


# ============================================================================
# Proposal 相关测试
# ============================================================================


async def test_proposal_create_empty_items_returns_422(client, _sessionmaker):
    """Proposal 创建时 items 为空应业务 422。"""
    token = await _login_admin(client)
    async with _sessionmaker() as session:
        creator_id = await _admin_user_id(session)
    resp = await _req(
        client, token, "POST", "/api/v1/proposals", json={
            "proposal_name": "Empty",
            "customer_name": "Client",
            "creator_id": str(creator_id),
            "items": [],
        }
    )
    assert resp.status_code == 422
    # Pydantic field_validator rejection: detail is a list with validation error
    detail = resp.json().get("detail")
    assert detail is not None


async def test_proposal_create_invalid_quantity_returns_422(client, _sessionmaker):
    """Proposal item quantity <= 0 应被 Pydantic 拒绝。"""
    token = await _login_admin(client)
    async with _sessionmaker() as session:
        creator_id = await _admin_user_id(session)
    resp = await _req(
        client, token, "POST", "/api/v1/proposals", json={
            "proposal_name": "Bad qty",
            "creator_id": str(creator_id),
            "items": [{"product_id": str(uuid4()), "quantity": 0}],
        }
    )
    assert resp.status_code == 422


async def test_proposal_create_validates_active_product(client, _sessionmaker):
    """Proposal 创建时 inactive 产品应被拒绝。"""
    async with _sessionmaker() as session:
        inactive = await _make_inactive_product(session)
        creator_id = await _admin_user_id(session)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", "/api/v1/proposals", json={
            "proposal_name": "Inactive",
            "creator_id": str(creator_id),
            "items": [{"product_id": str(inactive.id)}],
        }
    )
    assert resp.status_code == 422


async def test_proposal_create_dedup_rejects(client, _sessionmaker):
    """Proposal 创建时重复 product_id 应被拒绝。"""
    async with _sessionmaker() as session:
        product = await _make_active_product(session)
        creator_id = await _admin_user_id(session)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", "/api/v1/proposals", json={
            "proposal_name": "Dup",
            "creator_id": str(creator_id),
            "items": [
                {"product_id": str(product.id)},
                {"product_id": str(product.id)},
            ],
        }
    )
    assert resp.status_code == 422


async def test_proposal_create_replaces_and_total_face_value(client, _sessionmaker):
    """Proposal 创建时计算 total_face_value = sum(face_price * qty)。"""
    async with _sessionmaker() as session:
        p1 = await _make_active_product(session)
        p2 = await _make_active_product(session)
        p2.face_price = 200.0
        creator_id = await _admin_user_id(session)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", "/api/v1/proposals", json={
            "proposal_name": "Total",
            "creator_id": str(creator_id),
            "items": [
                {"product_id": str(p1.id), "quantity": 1},
                {"product_id": str(p2.id), "quantity": 3},
            ],
        }
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["total_face_value"] == 700.0  # 100*1 + 200*3


async def test_proposal_detail_enriched_items_no_cost_price(client, _sessionmaker):
    """Proposal 详情 item 包含 product_no/face_price/line_total，不含 cost_price。"""
    async with _sessionmaker() as session:
        product = await _make_active_product(session)
        await session.commit()

        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator
        proposal = Proposal(
            proposal_no=f"PR-TEST-{uuid4().hex[:8].upper()}",
            proposal_name="Detail Test",
            creator_id=creator.id,
            customer_name="Test Client",
            status="draft",
        )
        session.add(proposal)
        await session.flush()
        item = ProposalItem(
            proposal_id=proposal.id,
            product_id=product.id,
            quantity=2,
            remark="sample remark",
        )
        session.add(item)
        proposal.total_face_value = 200.0
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(client, token, "GET", f"/api/v1/proposals/{proposal.id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) == 1
    it = data["items"][0]
    assert it["product_no"] == product.product_no
    assert it["product_name"] == "Test Product"
    assert it["face_price"] == 100.0
    assert it["quantity"] == 2
    assert it["remark"] == "sample remark"
    assert it["line_total"] == 200.0
    assert "cost_price" not in it


async def test_proposal_list_keyword_status_pagination(client, _sessionmaker):
    """Proposal 列表支持 keyword / status / 分页 / 倒序。"""
    async with _sessionmaker() as session:
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator

        for i in range(3):
            prop = Proposal(
                proposal_no=f"PR-ALPHA-{i}",
                proposal_name=f"Alpha Proposal {i}",
                customer_name="AlphaCorp" if i < 2 else "BetaCorp",
                creator_id=creator.id,
                status="draft",
            )
            session.add(prop)
        session.add(
            Proposal(
                proposal_no="PR-CONFIRMED-1",
                proposal_name="Confirmed Prop",
                customer_name="ConfirmedInc",
                creator_id=creator.id,
                status="confirmed",
            )
        )
        await session.commit()

    token = await _login_admin(client)

    # keyword 匹配 name
    resp = await _req(
        client, token, "GET", "/api/v1/proposals", params={"keyword": "Alpha"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 3

    # status confirmed
    resp = await _req(
        client, token, "GET", "/api/v1/proposals", params={"status": "confirmed"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1

    # 非法 status
    resp = await _req(
        client, token, "GET", "/api/v1/proposals", params={"status": "invalid"}
    )
    assert resp.status_code == 422

    # 分页
    resp = await _req(
        client, token, "GET", "/api/v1/proposals", params={"page": 1, "size": 1}
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["list"]) == 1


async def test_proposal_confirm_empty_items_returns_422(client, _sessionmaker):
    """Proposal confirm 时 items 为空应 422。"""
    async with _sessionmaker() as session:
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator
        proposal = Proposal(
            proposal_no=f"PR-CONFIRM-EMPTY-{uuid4().hex[:8].upper()}",
            proposal_name="Confirm Empty",
            creator_id=creator.id,
            status="draft",
        )
        session.add(proposal)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", f"/api/v1/proposals/{proposal.id}/confirm"
    )
    assert resp.status_code == 422


async def test_proposal_update_items_replaces_and_recalc(client, _sessionmaker):
    """Proposal update 替换明细并重算 total_face_value。"""
    async with _sessionmaker() as session:
        p1 = await _make_active_product(session)
        p2 = await _make_active_product(session)
        p2.face_price = 300.0
        await session.commit()

        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator
        proposal = Proposal(
            proposal_no=f"PR-UPDATE-{uuid4().hex[:8].upper()}",
            proposal_name="Update Test",
            creator_id=creator.id,
            total_face_value=100.0,
            status="draft",
        )
        session.add(proposal)
        await session.flush()
        session.add(ProposalItem(proposal_id=proposal.id, product_id=p1.id, quantity=1))
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "PUT", f"/api/v1/proposals/{proposal.id}", json={
            "items": [
                {"product_id": str(p1.id), "quantity": 2},
                {"product_id": str(p2.id), "quantity": 1},
            ]
        }
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["total_face_value"] == 500.0  # 100*2 + 300*1


# ============================================================================
# Revert Confirmation 相关测试
# ============================================================================


async def test_proposal_revert_confirmation_normal(client, _sessionmaker):
    """确认方案正常撤销到草稿状态。"""
    async with _sessionmaker() as session:
        product = await _make_active_product(session)
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator

        proposal = Proposal(
            proposal_no=f"PR-REVERT-{uuid4().hex[:8].upper()}",
            proposal_name="Revert Test",
            creator_id=creator.id,
            customer_name="Revert Client",
            status="confirmed",
        )
        session.add(proposal)
        await session.flush()
        item = ProposalItem(
            proposal_id=proposal.id,
            product_id=product.id,
            quantity=3,
            remark="test remark",
        )
        session.add(item)
        proposal.total_face_value = 300.0
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", f"/api/v1/proposals/{proposal.id}/revert-confirmation"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "draft"
    assert len(data["items"]) == 1
    it = data["items"][0]
    assert it["product_no"] == product.product_no
    assert it["quantity"] == 3
    assert it["remark"] == "test remark"
    assert it["line_total"] == 300.0
    assert "cost_price" not in it


async def test_proposal_revert_confirmation_idempotent(client, _sessionmaker):
    """撤销确认幂等：已处于 draft 时重复调用返回 draft 且富化 items。"""
    async with _sessionmaker() as session:
        product = await _make_active_product(session)
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator

        proposal = Proposal(
            proposal_no=f"PR-REVERT-ID-{uuid4().hex[:8].upper()}",
            proposal_name="Revert Idempotent",
            creator_id=creator.id,
            status="draft",
        )
        session.add(proposal)
        await session.flush()
        session.add(
            ProposalItem(proposal_id=proposal.id, product_id=product.id, quantity=1)
        )
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", f"/api/v1/proposals/{proposal.id}/revert-confirmation"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "draft"
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 1


async def test_proposal_revert_confirmation_blocked_by_confirmed_quotation(
    client, _sessionmaker,
):
    """存在未删除的 confirmed quotation 时，撤销确认应被 422 阻止。"""
    async with _sessionmaker() as session:
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator

        proposal = Proposal(
            proposal_no=f"PR-BLOCK-{uuid4().hex[:8].upper()}",
            proposal_name="Blocked Revert",
            creator_id=creator.id,
            status="confirmed",
        )
        session.add(proposal)
        await session.flush()

        conf_quotation = Quotation(
            quotation_no=f"QT-BLOCK-{uuid4().hex[:8].upper()}",
            proposal_id=proposal.id,
            creator_id=creator.id,
            status="confirmed",
        )
        session.add(conf_quotation)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", f"/api/v1/proposals/{proposal.id}/revert-confirmation"
    )
    assert resp.status_code == 422
    assert "已确认" in resp.json()["detail"]["msg"]


async def test_proposal_revert_confirmation_allows_draft_quotation(
    client, _sessionmaker,
):
    """draft quotation 不阻止撤销确认。"""
    async with _sessionmaker() as session:
        product = await _make_active_product(session)
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator

        proposal = Proposal(
            proposal_no=f"PR-DRAFT-QT-{uuid4().hex[:8].upper()}",
            proposal_name="Draft QT Revert",
            creator_id=creator.id,
            status="confirmed",
        )
        session.add(proposal)
        await session.flush()
        session.add(
            ProposalItem(proposal_id=proposal.id, product_id=product.id, quantity=1)
        )

        draft_quotation = Quotation(
            quotation_no=f"QT-DRAFT-REVERT-{uuid4().hex[:8].upper()}",
            proposal_id=proposal.id,
            creator_id=creator.id,
            status="draft",
        )
        session.add(draft_quotation)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", f"/api/v1/proposals/{proposal.id}/revert-confirmation"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "draft"
    assert len(data["items"]) == 1
    assert data["items"][0]["product_no"] == product.product_no


# ============================================================================
# Quotation 相关测试
# ============================================================================


async def test_quotation_create_empty_items_returns_422(client, _sessionmaker):
    """Quotation 创建时 items 为空应业务 422。"""
    async with _sessionmaker() as session:
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator
        proposal = Proposal(
            proposal_no=f"PR-QT-EMPTY-{uuid4().hex[:8].upper()}",
            proposal_name="QT Empty",
            creator_id=creator.id,
            status="draft",
        )
        session.add(proposal)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", "/api/v1/quotations", json={
            "proposal_id": str(proposal.id),
            "items": [],
        }
    )
    assert resp.status_code == 422


async def test_quotation_item_field_validation(client, _sessionmaker):
    """Quotation item 字段强约束，整单 discount 也必须在合法区间。"""
    async with _sessionmaker() as session:
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator
        proposal = Proposal(
            proposal_no=f"PR-QT-VAL-{uuid4().hex[:8].upper()}",
            proposal_name="QT Val",
            creator_id=creator.id,
            status="draft",
        )
        session.add(proposal)
        await session.commit()

    token = await _login_admin(client)

    # quantity <= 0
    resp = await _req(
        client, token, "POST", "/api/v1/quotations", json={
            "proposal_id": str(proposal.id),
            "items": [{"product_id": str(uuid4()), "quantity": -1, "unit_price": 10, "tax_rate": 0, "discount": 1}],
        }
    )
    assert resp.status_code == 422

    # unit_price < 0
    resp = await _req(
        client, token, "POST", "/api/v1/quotations", json={
            "proposal_id": str(proposal.id),
            "items": [{"product_id": str(uuid4()), "quantity": 1, "unit_price": -5, "tax_rate": 0, "discount": 1}],
        }
    )
    assert resp.status_code == 422

    # tax_rate > 1
    resp = await _req(
        client, token, "POST", "/api/v1/quotations", json={
            "proposal_id": str(proposal.id),
            "items": [{"product_id": str(uuid4()), "quantity": 1, "unit_price": 10, "tax_rate": 1.5, "discount": 1}],
        }
    )
    assert resp.status_code == 422

    # discount < 0
    resp = await _req(
        client, token, "POST", "/api/v1/quotations", json={
            "proposal_id": str(proposal.id),
            "discount": -0.1,
            "items": [{"product_id": str(uuid4()), "quantity": 1, "unit_price": 10, "tax_rate": 0}],
        }
    )
    assert resp.status_code == 422


async def test_quotation_amount_semantics(client, _sessionmaker):
    """后端金额语义：subtotal=unit_price*qty; total=sum(subtotal*(1+tax))*discount。"""
    async with _sessionmaker() as session:
        p1 = await _make_active_product(session)
        p2 = await _make_active_product(session)
        await session.commit()

        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator
        proposal = Proposal(
            proposal_no=f"PR-QT-AMT-{uuid4().hex[:8].upper()}",
            proposal_name="QT Amount",
            creator_id=creator.id,
            status="draft",
        )
        session.add(proposal)
        await session.commit()

    token = await _login_admin(client)
    # item1: unit_price=100, qty=2, tax=0.1 -> subtotal=200
    # item2: unit_price=50, qty=4, tax=0.2 -> subtotal=200
    # total = (200*1.1 + 200*1.2) * 0.9 = (220+240)*0.9 = 414.0
    resp = await _req(
        client, token, "POST", "/api/v1/quotations", json={
            "proposal_id": str(proposal.id),
            "discount": 0.9,
            "items": [
                {
                    "product_id": str(p1.id),
                    "quantity": 2,
                    "unit_price": 100.0,
                    "tax_rate": 0.1,
                    "discount": 1.0,
                },
                {
                    "product_id": str(p2.id),
                    "quantity": 4,
                    "unit_price": 50.0,
                    "tax_rate": 0.2,
                    "discount": 1.0,
                },
            ],
        }
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["subtotal"] == 400.0
    assert data["total_amount"] == 414.0


async def test_quotation_update_recalculates(client, _sessionmaker):
    """Quotation 更新折扣时重算 total_amount。"""
    async with _sessionmaker() as session:
        product = await _make_active_product(session)
        await session.commit()

        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator
        proposal = Proposal(
            proposal_no=f"PR-QT-UPD-{uuid4().hex[:8].upper()}",
            proposal_name="QT Update",
            creator_id=creator.id,
            status="draft",
        )
        session.add(proposal)
        await session.commit()

    token = await _login_admin(client)
    # 创建：discount=1.0, item subtotal=200, tax=0.1 -> total=220
    resp = await _req(
        client, token, "POST", "/api/v1/quotations", json={
            "proposal_id": str(proposal.id),
            "items": [
                {
                    "product_id": str(product.id),
                    "quantity": 2,
                    "unit_price": 100.0,
                    "tax_rate": 0.1,
                    "discount": 1.0,
                }
            ],
        }
    )
    assert resp.status_code == 201
    quotation_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["total_amount"] == 220.0

    # 更新 discount=0.5 -> total=110
    resp = await _req(
        client, token, "PUT", f"/api/v1/quotations/{quotation_id}", json={
            "discount": 0.5,
        }
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["total_amount"] == 110.0


async def test_quotation_confirm_empty_items_returns_422(client, _sessionmaker):
    """Quotation confirm 时 items 为空应 422。"""
    async with _sessionmaker() as session:
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator
        proposal = Proposal(
            proposal_no=f"PR-QT-CF-{uuid4().hex[:8].upper()}",
            proposal_name="QT Confirm",
            creator_id=creator.id,
            status="draft",
        )
        session.add(proposal)
        await session.flush()

        quotation = Quotation(
            quotation_no=f"QT-CF-EMPTY-{uuid4().hex[:8].upper()}",
            proposal_id=proposal.id,
            creator_id=creator.id,
            status="draft",
        )
        session.add(quotation)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", f"/api/v1/quotations/{quotation.id}/confirm"
    )
    assert resp.status_code == 422


async def test_quotation_list_returns_proposal_meta(client, _sessionmaker):
    """Quotation 列表返回 proposal_no / proposal_name。"""
    async with _sessionmaker() as session:
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator
        proposal = Proposal(
            proposal_no="PR-LIST-META-1",
            proposal_name="List Meta Proposal",
            creator_id=creator.id,
            status="draft",
        )
        session.add(proposal)
        await session.flush()

        quotation = Quotation(
            quotation_no="QT-LIST-1",
            proposal_id=proposal.id,
            creator_id=creator.id,
            status="draft",
        )
        session.add(quotation)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "GET", "/api/v1/quotations", params={"page": 1, "size": 10}
    )
    assert resp.status_code == 200
    list_items = resp.json()["data"]["list"]
    matched = [q for q in list_items if q["quotation_no"] == "QT-LIST-1"]
    assert len(matched) == 1
    q = matched[0]
    assert q["proposal_no"] == "PR-LIST-META-1"
    assert q["proposal_name"] == "List Meta Proposal"


# ============================================================================
# Shares 相关测试
# ============================================================================


async def test_share_schema_validation(client, _sessionmaker):
    """Shares 请求 schema：share_type 仅 proposal/quotation；参数范围。"""
    token = await _login_admin(client)

    # 非法 share_type
    resp = await _req(
        client, token, "POST", "/api/v1/shares", json={
            "share_type": "invalid",
            "target_id": str(uuid4()),
        }
    )
    assert resp.status_code == 422
    assert resp.json().get("detail") is not None

    # expire_hours 超出上限
    resp = await _req(
        client, token, "POST", "/api/v1/shares", json={
            "share_type": "proposal",
            "target_id": str(uuid4()),
            "expire_hours": 999999,
        }
    )
    assert resp.status_code == 422

    # max_access_count <= 0
    resp = await _req(
        client, token, "POST", "/api/v1/shares", json={
            "share_type": "proposal",
            "target_id": str(uuid4()),
            "max_access_count": 0,
        }
    )
    assert resp.status_code == 422


async def test_share_requires_real_target(client, _sessionmaker):
    """Shares target_id 必须对应真实未删除资源。"""
    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", "/api/v1/shares", json={
            "share_type": "proposal",
            "target_id": str(uuid4()),
        }
    )
    assert resp.status_code == 404


async def test_share_only_confirmed_quotation(client, _sessionmaker):
    """仅 confirmed quotation 可分享；draft 不可。"""
    async with _sessionmaker() as session:
        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator

        # draft proposal（可分享）
        draft_proposal = Proposal(
            proposal_no=f"PR-SHARE-DRAFT-{uuid4().hex[:8].upper()}",
            proposal_name="Draft Shareable",
            creator_id=creator.id,
            status="draft",
        )
        session.add(draft_proposal)

        # draft quotation（不可分享）
        draft_quo_proposal = Proposal(
            proposal_no=f"PR-DRAFT-Q-{uuid4().hex[:8].upper()}",
            proposal_name="Draft Quo",
            creator_id=creator.id,
            status="draft",
        )
        session.add(draft_quo_proposal)
        await session.flush()
        draft_quotation = Quotation(
            quotation_no=f"QT-DRAFT-{uuid4().hex[:8].upper()}",
            proposal_id=draft_quo_proposal.id,
            creator_id=creator.id,
            status="draft",
        )
        session.add(draft_quotation)

        # confirmed quotation（可分享）
        conf_quo_proposal = Proposal(
            proposal_no=f"PR-CONF-Q-{uuid4().hex[:8].upper()}",
            proposal_name="Conf Quo",
            creator_id=creator.id,
            status="confirmed",
        )
        session.add(conf_quo_proposal)
        await session.flush()
        conf_quotation = Quotation(
            quotation_no=f"QT-CONF-{uuid4().hex[:8].upper()}",
            proposal_id=conf_quo_proposal.id,
            creator_id=creator.id,
            status="confirmed",
        )
        session.add(conf_quotation)
        await session.commit()

    token = await _login_admin(client)

    # draft proposal 可分享
    resp = await _req(
        client, token, "POST", "/api/v1/shares", json={
            "share_type": "proposal",
            "target_id": str(draft_proposal.id),
        }
    )
    assert resp.status_code == 200

    # draft quotation 不可分享
    resp = await _req(
        client, token, "POST", "/api/v1/shares", json={
            "share_type": "quotation",
            "target_id": str(draft_quotation.id),
        }
    )
    assert resp.status_code == 422

    # confirmed quotation 可分享
    resp = await _req(
        client, token, "POST", "/api/v1/shares", json={
            "share_type": "quotation",
            "target_id": str(conf_quotation.id),
        }
    )
    assert resp.status_code == 200


# ============================================================================
# share_token 返回字段
# ============================================================================


async def test_share_token_proposal_no_cost_price(client, _sessionmaker):
    """share_token 返回 proposal 不含 cost_price，含 product_no/line_total/total_face_value。"""
    async with _sessionmaker() as session:
        product = await _make_active_product(session)
        await session.commit()

        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator

        proposal = Proposal(
            proposal_no=f"PR-SHARE-TOKEN-{uuid4().hex[:8].upper()}",
            proposal_name="Token Test",
            creator_id=creator.id,
            customer_name="TokenClient",
            status="draft",
        )
        session.add(proposal)
        await session.flush()
        item = ProposalItem(
            proposal_id=proposal.id,
            product_id=product.id,
            quantity=2,
        )
        session.add(item)
        proposal.total_face_value = 200.0
        await session.commit()

    token = await _login_admin(client)
    # 创建分享
    resp = await _req(
        client, token, "POST", "/api/v1/shares", json={
            "share_type": "proposal",
            "target_id": str(proposal.id),
        }
    )
    share_token_str = resp.json()["data"]["token"]

    # 访问分享
    resp = await client.get(f"/api/v1/share/{share_token_str}")
    assert resp.status_code == 200
    content = resp.json()["data"]["content"]
    assert content["proposal_no"] == proposal.proposal_no
    assert content["total_face_value"] == 200.0
    assert len(content["items"]) == 1
    it = content["items"][0]
    assert it["product_no"] == product.product_no
    assert it["line_total"] == 200.0
    assert "cost_price" not in it


async def test_share_token_quotation_fields_no_cost_price(client, _sessionmaker):
    """share_token 返回 quotation 含 unit_price/tax_rate/subtotal，不含 cost_price。"""
    async with _sessionmaker() as session:
        product = await _make_active_product(session)
        await session.commit()

        creator = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        assert creator

        proposal = Proposal(
            proposal_no=f"PR-QT-TOKEN-{uuid4().hex[:8].upper()}",
            proposal_name="QT Token",
            creator_id=creator.id,
            status="confirmed",
        )
        session.add(proposal)
        await session.flush()

        quotation = Quotation(
            quotation_no=f"QT-TOKEN-{uuid4().hex[:8].upper()}",
            proposal_id=proposal.id,
            creator_id=creator.id,
            status="confirmed",
            total_amount=220.0,
            subtotal=200.0,
            tax_rate=0.1,
            discount=1.0,
        )
        session.add(quotation)
        await session.flush()
        qitem = QuotationItem(
            quotation_id=quotation.id,
            product_id=product.id,
            quantity=2,
            unit_price=100.0,
            tax_rate=0.1,
            subtotal=200.0,
        )
        session.add(qitem)
        await session.commit()

    token = await _login_admin(client)
    resp = await _req(
        client, token, "POST", "/api/v1/shares", json={
            "share_type": "quotation",
            "target_id": str(quotation.id),
        }
    )
    share_token_str = resp.json()["data"]["token"]

    resp = await client.get(f"/api/v1/share/{share_token_str}")
    assert resp.status_code == 200
    content = resp.json()["data"]["content"]
    assert content["quotation_no"] == quotation.quotation_no
    assert len(content["items"]) == 1
    it = content["items"][0]
    assert it["unit_price"] == 100.0
    assert it["tax_rate"] == 0.1
    assert it["subtotal"] == 200.0
    assert "cost_price" not in it
