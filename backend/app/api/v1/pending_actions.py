from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.models.ai_action import PendingAction
from app.schemas.pending_action import PendingActionConfirm, PendingActionCreate
from app.services.pending_actions import (
    action_to_dict,
    cancel_pending_action,
    confirm_pending_action,
    create_pending_action,
)

router = APIRouter()


def _user_id(current_user: dict) -> UUID:
    raw = current_user.get("sub") or current_user.get("user_id")
    if not raw:
        raise HTTPException(status_code=401, detail={"code": 40101, "msg": "未登录 / Token 无效"})
    return UUID(str(raw))


def _envelope(data, code: int = 200, msg: str = "success") -> dict:
    return {"code": code, "data": data, "msg": msg}


def _ensure_enabled() -> None:
    if not settings.AI_PENDING_ACTIONS_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CAPABILITY_DISABLED",
                "msg": "AI 待确认动作已关闭",
                "retryable": False,
            },
        )


@router.get("", response_model=dict)
async def list_pending_actions(
    status: str | None = Query(default="pending"),
    current_user: dict = Depends(PermissionChecker("ai:pending_action")),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    stmt = select(PendingAction).where(PendingAction.is_deleted.is_(False))
    if current_user.get("role_code") != "admin":
        stmt = stmt.where(PendingAction.created_by == _user_id(current_user))
    if status:
        stmt = stmt.where(PendingAction.status == status)
    rows = (
        (await db.execute(stmt.order_by(PendingAction.create_time.desc()).limit(100)))
        .scalars()
        .all()
    )
    return _envelope({"list": [action_to_dict(row) for row in rows]})


@router.post("", response_model=dict, status_code=201)
async def create_action(
    body: PendingActionCreate,
    current_user: dict = Depends(PermissionChecker("ai:pending_action")),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    action = await create_pending_action(db, body, _user_id(current_user))
    await db.commit()
    await db.refresh(action)
    return _envelope(action_to_dict(action))


@router.get("/{action_id}", response_model=dict)
async def get_action(
    action_id: UUID,
    current_user: dict = Depends(PermissionChecker("ai:pending_action")),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    stmt = select(PendingAction).where(
        PendingAction.id == action_id, PendingAction.is_deleted.is_(False)
    )
    if current_user.get("role_code") != "admin":
        stmt = stmt.where(PendingAction.created_by == _user_id(current_user))
    action = (await db.execute(stmt)).scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "待确认动作不存在"})
    return _envelope(action_to_dict(action))


@router.post("/{action_id}/confirm", response_model=dict)
async def confirm_action(
    action_id: UUID,
    body: PendingActionConfirm | None = None,
    current_user: dict = Depends(PermissionChecker("ai:pending_action")),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    action = await confirm_pending_action(
        db,
        action_id,
        _user_id(current_user),
        idempotency_key=body.idempotency_key if body else None,
    )
    return _envelope(action_to_dict(action))


@router.post("/{action_id}/cancel", response_model=dict)
async def cancel_action(
    action_id: UUID,
    current_user: dict = Depends(PermissionChecker("ai:pending_action")),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    action = await cancel_pending_action(db, action_id, _user_id(current_user))
    return _envelope(action_to_dict(action))
