"""提醒与通知 API（HLD §8.5）。"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.models.reminder import Notification, Reminder

router = APIRouter(prefix="/api/v1/reminders", tags=["reminders"])


def _user_id(current_user: dict) -> UUID:
    raw = current_user.get("sub") or current_user.get("user_id")
    if not raw:
        raise HTTPException(status_code=401, detail={"code": 40101, "msg": "未登录 / Token 无效"})
    return UUID(str(raw))


def _envelope(data, code: int = 200, msg: str = "success") -> dict:
    return {"code": code, "data": data, "msg": msg}


def _reminder_to_dict(r: Reminder) -> dict:
    return {
        "id": str(r.id),
        "rule_code": r.rule_code,
        "target_type": r.target_type,
        "target_id": str(r.target_id),
        "assignee_id": str(r.assignee_id),
        "title": r.title,
        "body": r.body,
        "due_at": r.due_at.isoformat() if r.due_at else None,
        "status": r.status,
        "dedupe_key": r.dedupe_key,
        "snoozed_until": r.snoozed_until.isoformat() if r.snoozed_until else None,
        "fired_at": r.fired_at.isoformat() if r.fired_at else None,
        "done_at": r.done_at.isoformat() if r.done_at else None,
        "attempts": r.attempts,
        "escalated": r.escalated,
        "payload": r.payload,
        "create_time": r.create_time.isoformat() if r.create_time else None,
    }


def _notification_to_dict(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "user_id": str(n.user_id),
        "title": n.title,
        "body": n.body,
        "kind": n.kind,
        "link": n.link,
        "reminder_id": str(n.reminder_id) if n.reminder_id else None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "create_time": n.create_time.isoformat() if n.create_time else None,
    }


@router.get("", response_model=dict)
async def list_reminders(
    status: str | None = Query(default="pending"),
    assignee_id: UUID | None = Query(default=None),
    current_user: dict = Depends(PermissionChecker("reminder:edit")),
    db: AsyncSession = Depends(get_db),
):
    uid = _user_id(current_user)
    role = current_user.get("role_code")

    stmt = select(Reminder).where(Reminder.is_deleted.is_(False))

    # Non-admin/manager can only see their own
    if role not in ("admin", "manager"):
        stmt = stmt.where(Reminder.assignee_id == uid)
    elif assignee_id:
        stmt = stmt.where(Reminder.assignee_id == assignee_id)

    if status:
        stmt = stmt.where(Reminder.status == status)

    rows = (await db.execute(stmt.order_by(Reminder.due_at).limit(100))).scalars().all()
    return _envelope({"list": [_reminder_to_dict(r) for r in rows], "total": len(rows)})


@router.post("/{reminder_id}/done", response_model=dict)
async def mark_done(
    reminder_id: UUID,
    current_user: dict = Depends(PermissionChecker("reminder:edit")),
    db: AsyncSession = Depends(get_db),
):
    uid = _user_id(current_user)
    role = current_user.get("role_code")

    stmt = select(Reminder).where(
        Reminder.id == reminder_id, Reminder.is_deleted.is_(False)
    )
    if role not in ("admin", "manager"):
        stmt = stmt.where(Reminder.assignee_id == uid)

    rem = (await db.execute(stmt)).scalar_one_or_none()
    if not rem:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "提醒不存在"})

    rem.status = "done"
    rem.done_at = datetime.utcnow()
    await db.commit()
    return _envelope(_reminder_to_dict(rem))


@router.post("/{reminder_id}/snooze", response_model=dict)
async def snooze(
    reminder_id: UUID,
    until: datetime = Query(..., description="Snooze until (ISO8601)"),
    current_user: dict = Depends(PermissionChecker("reminder:edit")),
    db: AsyncSession = Depends(get_db),
):
    uid = _user_id(current_user)
    role = current_user.get("role_code")

    stmt = select(Reminder).where(
        Reminder.id == reminder_id, Reminder.is_deleted.is_(False)
    )
    if role not in ("admin", "manager"):
        stmt = stmt.where(Reminder.assignee_id == uid)

    rem = (await db.execute(stmt)).scalar_one_or_none()
    if not rem:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "提醒不存在"})

    rem.status = "snoozed"
    rem.snoozed_until = until
    await db.commit()
    return _envelope(_reminder_to_dict(rem))


@router.post("/{reminder_id}/cancel", response_model=dict)
async def cancel(
    reminder_id: UUID,
    current_user: dict = Depends(PermissionChecker("reminder:edit")),
    db: AsyncSession = Depends(get_db),
):
    uid = _user_id(current_user)
    role = current_user.get("role_code")

    stmt = select(Reminder).where(
        Reminder.id == reminder_id, Reminder.is_deleted.is_(False)
    )
    if role not in ("admin", "manager"):
        stmt = stmt.where(Reminder.assignee_id == uid)

    rem = (await db.execute(stmt)).scalar_one_or_none()
    if not rem:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "提醒不存在"})

    rem.status = "cancelled"
    rem.done_at = datetime.utcnow()
    await db.commit()
    return _envelope(_reminder_to_dict(rem))


@router.get("/notifications", response_model=dict)
async def list_notifications(
    unread: bool = Query(default=False),
    current_user: dict = Depends(PermissionChecker("reminder:edit")),
    db: AsyncSession = Depends(get_db),
):
    uid = _user_id(current_user)
    stmt = select(Notification).where(
        Notification.user_id == uid,
        Notification.is_deleted.is_(False),
    )
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = (
        await db.execute(stmt.order_by(Notification.create_time.desc()).limit(100))
    ).scalars().all()
    return _envelope({"list": [_notification_to_dict(n) for n in rows], "total": len(rows)})


@router.post("/notifications/read", response_model=dict)
async def mark_notifications_read(
    body: dict,
    current_user: dict = Depends(PermissionChecker("reminder:edit")),
    db: AsyncSession = Depends(get_db),
):
    uid = _user_id(current_user)
    ids = body.get("ids")
    all_flag = body.get("all", False)

    if all_flag:
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == uid,
                Notification.read_at.is_(None),
                Notification.is_deleted.is_(False),
            )
            .values(read_at=datetime.utcnow())
        )
    elif ids:
        uuid_ids = [UUID(str(i)) for i in ids]
        stmt = (
            update(Notification)
            .where(
                Notification.id.in_(uuid_ids),
                Notification.user_id == uid,
                Notification.is_deleted.is_(False),
            )
            .values(read_at=datetime.utcnow())
        )
    else:
        raise HTTPException(status_code=422, detail={"code": 40001, "msg": "ids 或 all=true 必填"})

    result = await db.execute(stmt)
    await db.commit()
    return _envelope({"updated": result.rowcount})
