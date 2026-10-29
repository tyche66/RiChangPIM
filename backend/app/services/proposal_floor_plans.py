"""方案平面图读取与展示地址组装。

被三处复用：
* 后台方案详情（``api/v1/proposals.py``，登录用户 token）
* 公开分享页（``api/v1/share_token.py``，匿名短 token）
* 平面图自身的增删改查接口（``api/v1/proposal_floor_plans.py``）

URL 一律走 ``/api/v1/files/{attachment_id}/content?token=...``，绝不暴露 MinIO
地址；这与产品封面图、场景图的既有口径一致。
"""

from __future__ import annotations

import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.security import create_access_token
from app.models.sales import ProposalFloorPlan

PREVIEW_EXPIRE_SECONDS = 900
CONTENT_TOKEN_SCOPE = "file_content"


def content_url(attachment_id: UUID, *, subject: str | None = None) -> str:
    """签发一个短时只读的文件地址（默认 15 分钟）。"""
    token = create_access_token(
        {
            "sub": subject or "file-content",
            "scope": CONTENT_TOKEN_SCOPE,
            "attachment_id": str(attachment_id),
        },
        expires_delta=datetime.timedelta(seconds=PREVIEW_EXPIRE_SECONDS),
    )
    return f"/api/v1/files/{attachment_id}/content?token={token}"


async def load_floor_plans(
    db: AsyncSession, proposal_id: UUID
) -> list[ProposalFloorPlan]:
    """按展示顺序取一个方案下未删除的平面图（含附件）。"""
    result = await db.execute(
        select(ProposalFloorPlan)
        .options(joinedload(ProposalFloorPlan.attachment))
        .where(
            ProposalFloorPlan.proposal_id == proposal_id,
            ProposalFloorPlan.is_deleted.is_(False),
        )
        .order_by(ProposalFloorPlan.sort, ProposalFloorPlan.create_time)
    )
    return list(result.scalars().all())


def floor_plan_summary(pfp: ProposalFloorPlan, *, subject: str | None = None) -> dict:
    """单条平面图的对外形状（不含展示地址）。"""
    attachment = pfp.attachment
    return {
        "id": str(pfp.id),
        "proposal_id": str(pfp.proposal_id),
        "project_id": str(pfp.project_id) if pfp.project_id else None,
        "attachment_id": str(pfp.attachment_id),
        "name": pfp.name,
        "floor_label": pfp.floor_label,
        "space_label": pfp.space_label,
        "sort": pfp.sort,
        "file_name": attachment.file_name if attachment else None,
        "file_type": attachment.file_type if attachment else None,
        "file_size": attachment.file_size if attachment else None,
        "create_time": pfp.create_time.isoformat() if pfp.create_time else None,
    }


def floor_plan_payload(pfp: ProposalFloorPlan, *, subject: str | None = None) -> dict:
    """对外形状 + 短时展示地址。"""
    data = floor_plan_summary(pfp, subject=subject)
    data["image_url"] = content_url(pfp.attachment_id, subject=subject)
    return data


__all__ = [
    "CONTENT_TOKEN_SCOPE",
    "PREVIEW_EXPIRE_SECONDS",
    "content_url",
    "floor_plan_payload",
    "floor_plan_summary",
    "load_floor_plans",
]
