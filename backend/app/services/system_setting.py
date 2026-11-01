"""全局设置服务（FR-3）。

* 单行表 ``system_setting``，``data`` JSONB 只存被显式改过的键；
  读取侧始终与 Schema 默认值合并，代码默认值是最终兜底。
* 进程内 60 秒缓存；保存后立即失效；多 worker 最迟 60 秒内一致。
* 行缺失时按默认值幂等创建（启动、读取、保存三条路径都兜），
  并发创建由迁移 0039 的单行部分唯一索引兜底。
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Attachment
from app.models.system_setting import SystemSetting
from app.schemas.system_setting import (
    BrandSettings,
    BusinessSettings,
    PublicSettings,
    ShareSettings,
    SystemSettingRead,
    SystemSettingUpdate,
)

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60.0
LOGO_URL_PATH = "/api/v1/settings/logo"

_GROUPS = ("brand", "share", "business")


@dataclass(frozen=True)
class SettingsSnapshot:
    """一次合并后的设置视图 + 已解析的 Logo 身份信息。"""

    settings: SystemSettingRead
    logo_attachment_id: UUID | None
    logo_version: str | None
    logo_updated_at: datetime | None


def logo_version_for(attachment_id: UUID, update_time: datetime) -> str:
    """``v`` 由附件 ID + 更新时间生成：Logo 更新后 URL 随之变化。"""
    material = f"{attachment_id}|{update_time.isoformat()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# 进程内缓存
# ---------------------------------------------------------------------------

_cache_snapshot: SettingsSnapshot | None = None
_cache_expires_at: float = 0.0


def invalidate_cache() -> None:
    """保存设置后立即失效；其他 worker 靠 TTL 最迟 60 秒追平。"""
    global _cache_snapshot, _cache_expires_at
    _cache_snapshot = None
    _cache_expires_at = 0.0


# ---------------------------------------------------------------------------
# 读取与合并
# ---------------------------------------------------------------------------


async def _load_row(db: AsyncSession) -> SystemSetting:
    """取唯一一行；无行则按默认值创建（幂等，含并发兜底）。"""
    result = await db.execute(
        select(SystemSetting)
        .where(SystemSetting.is_deleted.is_(False))
        .order_by(SystemSetting.create_time)
        .limit(1)
    )
    row = result.scalars().first()
    if row is not None:
        return row
    row = SystemSetting(data={})
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # 并发创建：唯一索引只放行一行，回滚后改读对方写入的行。
        await db.rollback()
        result = await db.execute(
            select(SystemSetting)
            .where(SystemSetting.is_deleted.is_(False))
            .order_by(SystemSetting.create_time)
            .limit(1)
        )
        row = result.scalars().first()
        if row is None:
            raise
    return row


def _merge_group(raw: dict[str, Any], group: str, defaults: dict[str, Any]) -> dict[str, Any]:
    """以代码默认值打底，叠加存储值；未知键忽略（写入侧才做拒绝）。"""
    merged = dict(defaults)
    stored = raw.get(group)
    if isinstance(stored, dict):
        for key, value in stored.items():
            if key in defaults:
                merged[key] = value
    return merged


def _build_snapshot(raw: dict[str, Any]) -> SystemSettingRead:
    base = SystemSettingRead()
    try:
        return SystemSettingRead(
            brand=_merge_group(raw, "brand", base.brand.model_dump()),
            share=_merge_group(raw, "share", base.share.model_dump()),
            business=_merge_group(raw, "business", base.business.model_dump()),
        )
    except ValidationError:
        # 历史脏数据只在告警里可见，读取绝不 500：坏分组回落默认值。
        logger.warning("system_setting 数据校验失败，回落默认值", exc_info=True)
        return base


async def get_snapshot(db: AsyncSession) -> SettingsSnapshot:
    """带 60 秒缓存的合并视图；无 Logo 或附件已删时 Logo 字段为空。"""
    global _cache_snapshot, _cache_expires_at
    now = time.monotonic()
    if _cache_snapshot is not None and now < _cache_expires_at:
        return _cache_snapshot

    row = await _load_row(db)
    settings = _build_snapshot(dict(row.data or {}))

    logo_attachment_id = settings.brand.logo_attachment_id
    logo_version: str | None = None
    logo_updated_at: datetime | None = None
    if logo_attachment_id is not None:
        attachment = (
            await db.execute(
                select(Attachment).where(
                    Attachment.id == logo_attachment_id,
                    Attachment.is_deleted.is_(False),
                )
            )
        ).scalars().first()
        if attachment is not None and attachment.update_time is not None:
            logo_version = logo_version_for(attachment.id, attachment.update_time)
            logo_updated_at = attachment.update_time
        else:
            logo_attachment_id = None

    snapshot = SettingsSnapshot(
        settings=settings,
        logo_attachment_id=logo_attachment_id,
        logo_version=logo_version,
        logo_updated_at=logo_updated_at,
    )
    _cache_snapshot = snapshot
    _cache_expires_at = now + CACHE_TTL_SECONDS
    return snapshot


async def get_settings(db: AsyncSession) -> SystemSettingRead:
    return (await get_snapshot(db)).settings


async def get_share_defaults(db: AsyncSession) -> ShareSettings:
    """分享缺省值（expire_hours / max_access_count / require_password）。"""
    return (await get_snapshot(db)).share


async def get_business_defaults(db: AsyncSession) -> BusinessSettings:
    """业务缺省值（默认税率 / 金额小数位 / 货币符号）。"""
    return (await get_snapshot(db)).business


async def get_public_settings(db: AsyncSession) -> PublicSettings:
    """匿名品牌字段：绝不携带 share/business 配置。"""
    snapshot = await get_snapshot(db)
    brand = snapshot.settings.brand
    logo_url = (
        f"{LOGO_URL_PATH}?v={snapshot.logo_version}" if snapshot.logo_version else None
    )
    return PublicSettings(
        site_name=brand.site_name,
        portal_title=brand.portal_title,
        portal_subtitle=brand.portal_subtitle,
        footer_text=brand.footer_text,
        logo_url=logo_url,
    )


async def get_logo_attachment(db: AsyncSession) -> tuple[Attachment, str] | None:
    """当前配置的 Logo 附件与版本号；未配置/已删返回 None。"""
    snapshot = await get_snapshot(db)
    if snapshot.logo_attachment_id is None or snapshot.logo_version is None:
        return None
    attachment = (
        await db.execute(
            select(Attachment).where(
                Attachment.id == snapshot.logo_attachment_id,
                Attachment.is_deleted.is_(False),
            )
        )
    ).scalars().first()
    if attachment is None:
        return None
    return attachment, snapshot.logo_version


# ---------------------------------------------------------------------------
# 保存
# ---------------------------------------------------------------------------


def _apply_update(raw: dict[str, Any], payload: SystemSettingUpdate) -> dict[str, Any]:
    """嵌套局部更新：未出现的字段保持原值；显式 null 除 Logo 外一律视为不动。

    ``mode="json"`` 让 UUID 落成字符串，保证 JSONB 可序列化。
    """
    dump = payload.model_dump(exclude_unset=True, mode="json")
    result = dict(raw)
    for group in _GROUPS:
        fields = dump.get(group)
        if not isinstance(fields, dict):
            continue
        bucket = dict(result.get(group) or {})
        for key, value in fields.items():
            if value is None and not (group == "brand" and key == "logo_attachment_id"):
                continue
            bucket[key] = value
        result[group] = bucket
    return result


async def save_settings(db: AsyncSession, payload: SystemSettingUpdate) -> SystemSettingRead:
    """合并-校验-落库-失效缓存，返回保存后的生效视图。

    只把被显式改过的键写回 JSONB（增量存储），管理员没碰过的键继续跟随
    代码默认值；合并视图校验失败只影响读取兜底，不会静默改写存储。
    """
    row = await _load_row(db)
    raw = _apply_update(dict(row.data or {}), payload)
    merged = _build_snapshot(raw)
    row.data = _clean_stored(raw)
    await db.commit()
    invalidate_cache()
    return merged.settings


_KNOWN_FIELDS: dict[str, set[str]] = {
    "brand": set(BrandSettings.model_fields),
    "share": set(ShareSettings.model_fields),
    "business": set(BusinessSettings.model_fields),
}


def _clean_stored(raw: dict[str, Any]) -> dict[str, Any]:
    """只保留已知分组/键，存储层永不积累未知键。"""
    cleaned: dict[str, Any] = {}
    for group, keys in _KNOWN_FIELDS.items():
        stored = raw.get(group)
        if isinstance(stored, dict):
            bucket = {k: v for k, v in stored.items() if k in keys}
            if bucket:
                cleaned[group] = bucket
    return cleaned


async def ensure_default_row(db: AsyncSession) -> None:
    """启动兜底：无行则创建默认行（幂等）。"""
    await _load_row(db)
