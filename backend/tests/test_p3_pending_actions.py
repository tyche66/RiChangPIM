from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models.ai_action import PendingAction
from app.models.product import Brand, Category, Product, Supplier
from app.models.sales import Proposal
from app.models.user import User

pytestmark = pytest.mark.anyio


async def _login_admin(client) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


async def _admin_user_id(session):
    user = (await session.execute(select(User).where(User.username == "admin"))).scalar_one()
    return user.id


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_product(session, *, stock_status="in_stock", face_price=100.0):
    brand = Brand(brand_name=f"brand-{uuid4().hex[:8]}")
    supplier = Supplier(supplier_name=f"supplier-{uuid4().hex[:8]}")
    category = Category(category_name=f"cat-{uuid4().hex[:8]}", level=1, sort=0)
    session.add_all([brand, supplier, category])
    await session.flush()
    product = Product(
        product_no=f"P3-{uuid4().hex[:8].upper()}",
        product_name="P3 Test Product",
        brand_id=brand.id,
        supplier_id=supplier.id,
        category_id=category.id,
        face_price=face_price,
        cost_price=60.0,
        stock_status=stock_status,
        status="active",
        completeness_status="pending" if face_price == 99999 else "complete",
    )
    session.add(product)
    await session.flush()
    return product


async def _proposal_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Proposal))


async def test_gateway_creates_pending_action_without_writing_proposal(client, _sessionmaker):
    async with _sessionmaker() as session:
        product = await _make_product(session)
        before = await _proposal_count(session)
        await session.commit()

    token = await _login_admin(client)
    resp = await client.post(
        "/api/v1/knowledge/query",
        headers=_headers(token),
        json={
            "message": f"请创建方案草稿 {product.product_no}",
            "capabilities": {"supports_actions": True},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["pending_actions"]) == 1
    assert data["pending_actions"][0]["action_type"] == "proposal.create_draft"
    assert "确认前不会写入" in data["answer"]

    async with _sessionmaker() as session:
        assert await _proposal_count(session) == before


async def test_confirm_pending_action_creates_traceable_proposal_and_is_idempotent(
    client, _sessionmaker
):
    token = await _login_admin(client)
    async with _sessionmaker() as session:
        product = await _make_product(session)
        user_id = await _admin_user_id(session)
        await session.commit()

    create_resp = await client.post(
        "/api/v1/ai/actions",
        headers=_headers(token),
        json={
            "action_type": "proposal.create_draft",
            "idempotency_key": f"idem-{uuid4().hex}",
            "target_type": "proposal",
            "payload": {
                "proposal_name": "P3 AI Draft",
                "summary": "AI generated draft summary",
                "items": [{"product_id": str(product.id), "quantity": 2}],
            },
            "source_ids": ["db_product_x"],
            "model_name": "test-chat-model",
        },
    )
    assert create_resp.status_code == 201
    action = create_resp.json()["data"]

    first = await client.post(f"/api/v1/ai/actions/{action['id']}/confirm", headers=_headers(token))
    second = await client.post(
        f"/api/v1/ai/actions/{action['id']}/confirm", headers=_headers(token)
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["result"] == second.json()["data"]["result"]

    async with _sessionmaker() as session:
        proposals = (
            (await session.execute(select(Proposal).where(Proposal.proposal_name == "P3 AI Draft")))
            .scalars()
            .all()
        )
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal.creator_id == user_id
        assert proposal.ai_polished is True
        assert proposal.ai_polish_model == "test-chat-model"
        assert proposal.ai_source_ids == ["db_product_x"]
        assert proposal.ai_confirmed_by == user_id
        assert proposal.total_face_value == 200.0


async def test_expired_pending_action_does_not_write(client, _sessionmaker):
    token = await _login_admin(client)
    async with _sessionmaker() as session:
        product = await _make_product(session)
        await session.commit()

    create_resp = await client.post(
        "/api/v1/ai/actions",
        headers=_headers(token),
        json={
            "action_type": "proposal.create_draft",
            "idempotency_key": f"idem-{uuid4().hex}",
            "payload": {"items": [{"product_id": str(product.id), "quantity": 1}]},
            "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        },
    )
    action_id = create_resp.json()["data"]["id"]
    confirm = await client.post(f"/api/v1/ai/actions/{action_id}/confirm", headers=_headers(token))
    assert confirm.status_code == 409

    async with _sessionmaker() as session:
        action = await session.get(PendingAction, UUID(action_id))
        assert action.status == "expired"
        assert await _proposal_count(session) == 0


async def test_update_action_detects_object_status_conflict(client, _sessionmaker):
    token = await _login_admin(client)
    async with _sessionmaker() as session:
        product = await _make_product(session)
        user_id = await _admin_user_id(session)
        proposal = Proposal(
            proposal_no=f"PR-TEST-{uuid4().hex[:8]}",
            proposal_name="Conflict Target",
            creator_id=user_id,
            status="confirmed",
        )
        session.add(proposal)
        await session.commit()

    create_resp = await client.post(
        "/api/v1/ai/actions",
        headers=_headers(token),
        json={
            "action_type": "proposal.update_draft",
            "idempotency_key": f"idem-{uuid4().hex}",
            "target_type": "proposal",
            "target_id": str(proposal.id),
            "payload": {"items": [{"product_id": str(product.id), "quantity": 1}]},
        },
    )
    action_id = create_resp.json()["data"]["id"]
    confirm = await client.post(f"/api/v1/ai/actions/{action_id}/confirm", headers=_headers(token))
    assert confirm.status_code == 409

    async with _sessionmaker() as session:
        action = await session.get(PendingAction, UUID(action_id))
        assert action.status == "conflict"


async def test_procurement_compare_marks_missing_dynamic_fields_unknown(client, _sessionmaker):
    async with _sessionmaker() as session:
        product = await _make_product(session, stock_status="unknown")
        await session.commit()

    token = await _login_admin(client)
    resp = await client.post(
        "/api/v1/knowledge/query",
        headers=_headers(token),
        json={"message": f"采购比较供应商 {product.product_no} 的交期和质量"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "unknown" in data["answer"]
    supplier_facts = [f for f in data["facts"] if f["name"] == "supplier_compare"]
    assert supplier_facts
    value = supplier_facts[0]["value"]
    assert value["lead_time"] == "unknown"
    assert value["quality_rating"] == "unknown"
    assert value["realtime_stock"] == "unknown"
