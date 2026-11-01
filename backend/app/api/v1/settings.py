"""全局设置 API（FR-3）。

* ``GET  /api/v1/settings``         —— 管理员读取全部设置（含生成的 Logo URL）；
* ``PUT  /api/v1/settings``         —— 管理员嵌套局部更新，写审计日志；
* ``GET  /api/v1/settings/public``  —— 匿名品牌字段（绝不带分享/业务配置）；
* ``GET  /api/v1/settings/logo``    —— 匿名读取当前配置的 Logo（带版本号）。

安全边界：
* 管理员接口显式断言 ``role_code == "admin"``（同 ai_config._require_admin）；
* Logo 只服务当前配置的那一张图，JPG/PNG/WebP，单张 ≤2MB（保存时校验，
  读取侧再兜底一次扩展名检查，杜绝 SVG 之类的伪装类型被当作 Logo 输出）。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from email.utils import format_datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.core.minio_client import get_minio_client
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.product import Attachment
from app.schemas.system_setting import SystemSettingRead, SystemSettingUpdate
from app.services.system_setting import (
    get_logo_attachment,
    get_public_settings,
    get_settings,
    save_settings,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

LOGO_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
LOGO_MAX_BYTES = 2 * 1024 * 1024


def _envelope(data: Any, code: int = 200) -> dict:
    return {"code": code, "data": data}


def _require_admin(request: Request) -> None:
    """显式 admin 校验：PermissionChecker 对 admin 整体跳过权限码，
    因此这里必须单独断言 role_code，非管理员一律 403。"""
    if getattr(request.state, "role_code", None) != "admin":
        raise HTTPException(
            status_code=403, detail={"code": 40301, "msg": "无权限访问该资源"}
        )


def _logo_extension(attachment: Attachment) -> str | None:
    for source in (attachment.oss_key, attachment.file_name):
        suffix = str(source or "").rsplit(".", 1)[-1].lower()
        if suffix and suffix in LOGO_ALLOWED_EXTENSIONS:
            return suffix
    return None


def _logo_content_type(extension: str) -> str:
    if extension in {"jpg", "jpeg"}:
        return "image/jpeg"
    if extension == "png":
        return "image/png"
    return "image/webp"


async def _validate_logo_attachment(db: AsyncSession, attachment_id: uuid.UUID) -> None:
    """保存时校验 Logo 附件：存在、未删除、image、扩展名白名单、≤2MB。"""
    attachment = (
        await db.execute(
            select(Attachment).where(
                Attachment.id == attachment_id,
                Attachment.is_deleted.is_(False),
            )
        )
    ).scalars().first()
    if attachment is None:
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "Logo 附件不存在或已删除"}
        )
    if attachment.file_type != "image":
        raise HTTPException(
            status_code=422, detail={"code": 42202, "msg": "Logo 必须是图片附件"}
        )
    if _logo_extension(attachment) is None:
        raise HTTPException(
            status_code=422,
            detail={"code": 42203, "msg": "Logo 仅支持 JPG/PNG/WebP，不接受 SVG 等其他格式"},
        )
    if attachment.file_size > LOGO_MAX_BYTES:
        raise HTTPException(
            status_code=422, detail={"code": 42204, "msg": "Logo 图片不能超过 2MB"}
        )


def _settings_payload(settings: SystemSettingRead, logo_version: str | None) -> dict:
    data = settings.model_dump(mode="json")
    data["logo_url"] = f"/api/v1/settings/logo?v={logo_version}" if logo_version else None
    return data


@router.get(
    "",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("setting:view"))],
)
async def read_settings(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """管理员读取全部设置（含带版本号的 Logo URL）。"""
    _require_admin(request)
    settings = await get_settings(db)
    logo = await get_logo_attachment(db)
    logo_version = logo[1] if logo else None
    return _envelope(_settings_payload(settings, logo_version))


@router.put(
    "",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("setting:edit"))],
)
@audit_action("setting_update", module="settings")
async def update_settings(
    payload: SystemSettingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """嵌套局部更新：未出现的字段保持原值；未知 key 由 Schema 直接 422。"""
    _require_admin(request)
    if payload.brand is not None and "logo_attachment_id" in payload.brand.model_fields_set:
        if payload.brand.logo_attachment_id is not None:
            await _validate_logo_attachment(db, payload.brand.logo_attachment_id)
    settings = await save_settings(db, payload)
    logo = await get_logo_attachment(db)
    logo_version = logo[1] if logo else None
    return _envelope(_settings_payload(settings, logo_version))


@router.get("/public", response_model=dict)
async def read_public_settings(db: AsyncSession = Depends(get_db)) -> dict:
    """匿名品牌字段：site_name / portal_title / portal_subtitle / footer_text / logo_url。"""
    public = await get_public_settings(db)
    return _envelope(public.model_dump(mode="json"))


def _iter_minio_object(obj) -> Iterator[bytes]:
    try:
        yield from obj.stream(1024 * 1024)
    finally:
        obj.close()
        obj.release_conn()


def _cache_headers(etag: str, attachment: Attachment) -> dict[str, str]:
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    }
    if attachment.update_time is not None:
        headers["Last-Modified"] = format_datetime(
            attachment.update_time.astimezone(attachment.update_time.tzinfo), usegmt=True
        )
    return headers


@router.get("/logo")
async def read_logo(
    request: Request,
    v: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """匿名读取当前配置的 Logo；v 不匹配或未配置一律 404，门户回落打包资源。"""
    logo = await get_logo_attachment(db)
    if logo is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "未配置 Logo"})
    attachment, version = logo
    if v != version:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "Logo 版本不匹配"})

    extension = _logo_extension(attachment)
    if extension is None:
        # 保存侧已拦，读取侧兜底：宁可 404 也不把未知类型当图片发出去。
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "未配置 Logo"})

    etag = f'"{version}"'
    headers = _cache_headers(etag, attachment)
    if version in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)

    client = get_minio_client()
    try:
        obj = client.get_object(app_settings.MINIO_BUCKET, attachment.oss_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=404, detail={"code": 40402, "msg": "Logo 文件不存在或无法读取"}
        ) from exc

    filename = quote(str(attachment.file_name))
    headers["Content-Disposition"] = f"inline; filename*=UTF-8''{filename}"
    return StreamingResponse(
        _iter_minio_object(obj),
        media_type=_logo_content_type(extension),
        headers=headers,
    )
