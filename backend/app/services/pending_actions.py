from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ai_action import PendingAction
from app.models.product import Product
from app.models.sales import Proposal, ProposalItem
from app.schemas.pending_action import PendingActionCreate


def action_to_dict(action: PendingAction) -> dict[str, Any]:
    return {
        "id": str(action.id),
        "action_type": action.action_type,
        "status": action.status,
        "idempotency_key": action.idempotency_key,
        "target_type": action.target_type,
        "target_id": str(action.target_id) if action.target_id else None,
        "payload": action.payload or {},
        "source_ids": action.source_ids or [],
        "model_provider": action.model_provider,
        "model_name": action.model_name,
        "generation_version": action.generation_version,
        "reason": action.reason,
        "result": action.result,
        "created_by": str(action.created_by),
        "confirmed_by": str(action.confirmed_by) if action.confirmed_by else None,
        "confirmed_at": action.confirmed_at.isoformat() if action.confirmed_at else None,
        "expires_at": action.expires_at.isoformat() if action.expires_at else None,
        "create_time": action.create_time.isoformat() if action.create_time else None,
    }


async def create_pending_action(
    db: AsyncSession, data: PendingActionCreate, created_by: UUID
) -> PendingAction:
    existing = (
        await db.execute(
            select(PendingAction).where(
                PendingAction.idempotency_key == data.idempotency_key,
                PendingAction.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    action = PendingAction(
        action_type=data.action_type,
        idempotency_key=data.idempotency_key,
        target_type=data.target_type,
        target_id=data.target_id,
        payload=data.payload,
        source_ids=data.source_ids,
        model_provider=data.model_provider,
        model_name=data.model_name,
        generation_version=data.generation_version,
        reason=data.reason,
        created_by=created_by,
        expires_at=data.expires_at or datetime.now(UTC) + timedelta(hours=24),
    )
    db.add(action)
    await db.flush()
    return action


async def confirm_pending_action(
    db: AsyncSession,
    action_id: UUID,
    confirmed_by: UUID,
    *,
    idempotency_key: str | None = None,
) -> PendingAction:
    action = (
        await db.execute(
            select(PendingAction)
            .where(PendingAction.id == action_id, PendingAction.is_deleted.is_(False))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "待确认动作不存在"})
    if idempotency_key and action.idempotency_key != idempotency_key:
        raise HTTPException(status_code=409, detail={"code": 40901, "msg": "幂等键不匹配"})
    if action.status == "confirmed":
        return action
    if action.status != "pending":
        raise HTTPException(status_code=409, detail={"code": 40902, "msg": "动作状态不可确认"})
    if action.expires_at <= datetime.now(UTC):
        action.status = "expired"
        await db.commit()
        raise HTTPException(status_code=409, detail={"code": 40903, "msg": "动作已过期"})

    if action.action_type == "proposal.create_draft":
        result = await _confirm_create_proposal(db, action, confirmed_by)
    elif action.action_type == "proposal.update_draft":
        result = await _confirm_update_proposal(db, action, confirmed_by)
    else:
        raise HTTPException(status_code=422, detail={"code": 42201, "msg": "不支持的动作类型"})

    action.status = "confirmed"
    action.confirmed_by = confirmed_by
    action.confirmed_at = datetime.now(UTC)
    action.result = result
    await db.commit()
    await db.refresh(action)
    return action


async def cancel_pending_action(db: AsyncSession, action_id: UUID, user_id: UUID) -> PendingAction:
    action = (
        await db.execute(
            select(PendingAction).where(
                PendingAction.id == action_id,
                PendingAction.created_by == user_id,
                PendingAction.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "待确认动作不存在"})
    if action.status == "pending":
        action.status = "cancelled"
        await db.commit()
        await db.refresh(action)
    return action


async def _confirm_create_proposal(
    db: AsyncSession, action: PendingAction, confirmed_by: UUID
) -> dict[str, Any]:
    payload = action.payload or {}
    products = await _active_products(db, payload.get("items") or [])
    proposal = Proposal(
        proposal_no=f"PR-2026-{str(uuid4())[:8].upper()}",
        proposal_name=payload.get("proposal_name") or "AI 方案草稿",
        customer_name=payload.get("customer_name"),
        creator_id=confirmed_by,
        ai_polished=True,
        ai_polish_content=payload.get("summary"),
        ai_polish_at=datetime.now(UTC),
        ai_polish_model=action.model_name,
        ai_generation_version=action.generation_version,
        ai_source_ids=action.source_ids or [],
        ai_confirmed_by=confirmed_by,
    )
    db.add(proposal)
    await db.flush()
    proposal.total_face_value = _add_items(db, proposal.id, payload.get("items") or [], products)
    await db.flush()
    return {"proposal_id": str(proposal.id), "proposal_no": proposal.proposal_no}


async def _confirm_update_proposal(
    db: AsyncSession, action: PendingAction, confirmed_by: UUID
) -> dict[str, Any]:
    payload = action.payload or {}
    proposal_id = action.target_id or payload.get("proposal_id")
    proposal = (
        await db.execute(
            select(Proposal)
            .options(selectinload(Proposal.items))
            .where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not proposal:
        action.status = "conflict"
        await db.commit()
        raise HTTPException(status_code=409, detail={"code": 40904, "msg": "目标方案不存在"})
    if proposal.status != "draft":
        action.status = "conflict"
        await db.commit()
        raise HTTPException(status_code=409, detail={"code": 40905, "msg": "目标方案状态已变化"})
    expected = payload.get("expected_update_time")
    if expected and proposal.update_time.isoformat() != expected:
        action.status = "conflict"
        await db.commit()
        raise HTTPException(
            status_code=409, detail={"code": 40906, "msg": "目标方案已被其他操作修改"}
        )

    products = await _active_products(db, payload.get("items") or [])
    if payload.get("proposal_name"):
        proposal.proposal_name = payload["proposal_name"]
    if "customer_name" in payload:
        proposal.customer_name = payload.get("customer_name")
    if payload.get("items"):
        for item in list(proposal.items):
            await db.delete(item)
        proposal.total_face_value = _add_items(db, proposal.id, payload["items"], products)
    proposal.ai_polished = True
    proposal.ai_polish_content = payload.get("summary")
    proposal.ai_polish_at = datetime.now(UTC)
    proposal.ai_polish_model = action.model_name
    proposal.ai_generation_version = action.generation_version
    proposal.ai_source_ids = action.source_ids or []
    proposal.ai_confirmed_by = confirmed_by
    await db.flush()
    return {"proposal_id": str(proposal.id), "proposal_no": proposal.proposal_no}


async def _active_products(db: AsyncSession, items: list[dict[str, Any]]) -> dict[UUID, Product]:
    ids = [UUID(str(item["product_id"])) for item in items]
    if not ids:
        raise HTTPException(status_code=422, detail={"code": 42201, "msg": "方案明细不可为空"})
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail={"code": 42202, "msg": "方案明细产品不可重复"})
    products = (
        (
            await db.execute(
                select(Product).where(
                    Product.id.in_(ids),
                    Product.status == "active",
                    Product.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    found = {p.id: p for p in products}
    if set(ids) != set(found):
        raise HTTPException(status_code=422, detail={"code": 42203, "msg": "产品不存在或非激活"})
    return found


def _add_items(
    db: AsyncSession, proposal_id: UUID, items: list[dict[str, Any]], products: dict[UUID, Product]
) -> float:
    total = 0.0
    for idx, item in enumerate(items):
        product_id = UUID(str(item["product_id"]))
        quantity = int(item.get("quantity") or 1)
        if quantity < 1:
            raise HTTPException(status_code=422, detail={"code": 42204, "msg": "数量必须大于 0"})
        product = products[product_id]
        db.add(
            ProposalItem(
                proposal_id=proposal_id,
                product_id=product_id,
                quantity=quantity,
                sort=idx,
                remark=item.get("remark"),
            )
        )
        total += float(product.face_price) * quantity
    return round(total, 2)
