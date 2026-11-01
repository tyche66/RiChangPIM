"""后台公告 API（FR-4）。

管理接口（announcement:view / announcement:manage + 显式 admin 角色校验）：
    GET    /api/v1/announcements          列表，支持状态/受众筛选与分页
    POST   /api/v1/announcements          新建
    PUT    /api/v1/announcements/{id}     编辑
    DELETE /api/v1/announcements/{id}     软删除

公开接口（匿名）：
    GET    /api/v1/announcements/active?audience=admin|portal
           只返回 enabled、已到发布时间、未过期、受众匹配的公告；
           进程内缓存 60 秒，任意写操作后失效。

已读状态存浏览器 localStorage，服务端不建已读表。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.announcement import Announcement
from app.schemas.announcement import AnnouncementCreate, AnnouncementUpdate

router = APIRouter(prefix="/api/v1/announcements", tags=["announcements"])

CACHE_TTL_SECONDS = 60
# audience -> (monotonic 取时刻, payload)；任意写操作后整表失效。
_active_cache: dict[str, tuple[float, list[dict]]] = {}


def _now() -> datetime:
    return datetime.now(UTC)


def _envelope(data, code: int = 200, msg: str = "success") -> dict:
    return {"code": code, "data": data, "msg": msg}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _require_admin(request: Request, message: str = "仅系统管理员可执行该操作") -> None:
    if getattr(request.state, "role_code", None) != "admin":
        raise HTTPException(status_code=403, detail={"code": 40301, "msg": message})


def _derive_status(a: Announcement, now: datetime) -> str:
    """列表展示用的派生状态；草稿与手动停用统一归入 disabled。"""
    if not a.enabled:
        return "disabled"
    if a.publish_at and a.publish_at > now:
        return "scheduled"
    if a.expire_at and a.expire_at <= now:
        return "expired"
    return "active"


def _to_dict(a: Announcement, *, brief: bool = False) -> dict:
    data = {
        "id": str(a.id),
        "title": a.title,
        "audience": a.audience,
        "level": a.level,
        "enabled": a.enabled,
        "publish_at": _iso(a.publish_at),
        "expire_at": _iso(a.expire_at),
        "create_time": _iso(a.create_time),
        "update_time": _iso(a.update_time),
    }
    if not brief:
        data["content_md"] = a.content_md
        data["deleted_at"] = _iso(a.deleted_at)
        data["is_deleted"] = a.is_deleted
    return data


async def _get_alive(db: AsyncSession, announcement_id: UUID) -> Announcement:
    row = (
        await db.execute(
            select(Announcement).where(
                Announcement.id == announcement_id,
                Announcement.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "公告不存在"})
    return row


# /active 必须在 /{announcement_id} 之前声明，避免被路径参数吞掉。
@router.get("/active", response_model=dict)
async def list_active_announcements(
    audience: Literal["admin", "portal"] = Query(..., description="弹窗受众"),
    db: AsyncSession = Depends(get_db),
):
    """匿名接口：后台登录后与门户进入页面时都会调用，不要求登录态。"""
    cached = _active_cache.get(audience)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return _envelope({"list": cached[1]})

    rows = (
        (
            await db.execute(
                select(Announcement)
                .where(
                    Announcement.is_deleted.is_(False),
                    Announcement.enabled.is_(True),
                    Announcement.audience.in_([audience, "all"]),
                    (Announcement.publish_at.is_(None)) | (Announcement.publish_at <= func.now()),
                    (Announcement.expire_at.is_(None)) | (Announcement.expire_at > func.now()),
                )
                .order_by(
                    Announcement.publish_at.desc().nullslast(),
                    Announcement.create_time.desc(),
                )
            )
        )
        .scalars()
        .all()
    )

    data = [
        {
            "id": str(a.id),
            "title": a.title,
            "content_md": a.content_md,
            "level": a.level,
            "audience": a.audience,
            "publish_at": _iso(a.publish_at),
            "update_time": _iso(a.update_time),
        }
        for a in rows
    ]
    _active_cache[audience] = (time.monotonic(), data)
    return _envelope({"list": data})


@router.get("", response_model=dict)
async def list_announcements(
    status: Literal["active", "scheduled", "expired", "disabled"] | None = Query(default=None),
    audience: Literal["admin", "portal", "all"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_deleted: bool = Query(default=False, description="软删除追溯"),
    current_user: dict = Depends(PermissionChecker("announcement:view")),
    db: AsyncSession = Depends(get_db),
):
    if current_user.get("role_code") != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": 40301, "msg": "仅系统管理员可查看公告管理"},
        )

    stmt = select(Announcement)
    if not include_deleted:
        stmt = stmt.where(Announcement.is_deleted.is_(False))

    # 派生状态（active/scheduled/expired/disabled）难以压进单条 SQL 条件，
    # 公告量级很小，取元组后在内存里筛选再分页。
    rows = (await db.execute(stmt.order_by(Announcement.create_time.desc()))).scalars().all()
    now = _now()
    if status:
        rows = [a for a in rows if _derive_status(a, now) == status]
    if audience:
        rows = [a for a in rows if a.audience == audience]

    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    return _envelope({"list": [_to_dict(a) for a in page_rows], "total": total})


@router.post("", response_model=dict, status_code=201)
@audit_action("announcement_create", module="announcements", target_id_kwarg="id")
async def create_announcement(
    request: Request,
    body: AnnouncementCreate,
    current_user: dict = Depends(PermissionChecker("announcement:manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(request)
    row = Announcement(
        title=body.title,
        content_md=body.content_md,
        audience=body.audience,
        level=body.level,
        enabled=body.enabled,
        publish_at=body.publish_at,
        expire_at=body.expire_at,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    _active_cache.clear()
    return _envelope(_to_dict(row))


@router.put("/{announcement_id}", response_model=dict)
@audit_action("announcement_update", module="announcements", target_id_kwarg="id")
async def update_announcement(
    request: Request,
    announcement_id: UUID,
    body: AnnouncementUpdate,
    current_user: dict = Depends(PermissionChecker("announcement:manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(request)
    row = await _get_alive(db, announcement_id)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    if row.expire_at and row.publish_at and row.expire_at <= row.publish_at:
        raise HTTPException(
            status_code=422,
            detail={"code": 40001, "msg": "expire_at 必须晚于 publish_at"},
        )

    await db.commit()
    await db.refresh(row)
    _active_cache.clear()
    return _envelope(_to_dict(row))


@router.delete("/{announcement_id}", response_model=dict)
@audit_action("announcement_delete", module="announcements", target_id_kwarg="id")
async def delete_announcement(
    request: Request,
    announcement_id: UUID,
    current_user: dict = Depends(PermissionChecker("announcement:manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(request)
    row = await _get_alive(db, announcement_id)
    row.is_deleted = True
    row.deleted_at = _now()
    await db.commit()
    _active_cache.clear()
    return _envelope({"id": str(row.id)})
