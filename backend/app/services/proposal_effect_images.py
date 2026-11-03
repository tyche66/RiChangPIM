"""方案效果图读取与展示地址组装。

被三处复用：
* 后台方案详情（``api/v1/proposals.py``，登录用户 token）
* 公开分享页（``api/v1/share_token.py``，匿名短 token）
* 效果图自身的增删改查接口（``api/v1/proposal_effect_images.py``）

URL 一律走 ``/api/v1/files/{attachment_id}/content?token=...``，绝不暴露
MinIO 地址；这与产品封面图、场景图、平面图的既有口径一致。
效果图可绑定方案内的产品（product_id）或空间（楼层/空间标签快照），二者
独立可同时绑定；都不绑定说明是「方案整体」效果图。
"""

from __future__ import annotations

import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.security import create_access_token
from app.models.sales import ProposalEffectImage

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
        token_type="file_content",
    )
    return f"/api/v1/files/{attachment_id}/content?token={token}"


async def load_effect_images(
    db: AsyncSession, proposal_id: UUID
) -> list[ProposalEffectImage]:
    """按展示顺序取一个方案下未删除的效果图（含附件与绑定产品）。"""
    result = await db.execute(
        select(ProposalEffectImage)
        .options(
            joinedload(ProposalEffectImage.attachment),
            joinedload(ProposalEffectImage.product),
        )
        .where(
            ProposalEffectImage.proposal_id == proposal_id,
            ProposalEffectImage.is_deleted.is_(False),
        )
        .order_by(ProposalEffectImage.sort, ProposalEffectImage.create_time)
    )
    return list(result.scalars().all())


def effect_image_summary(
    pei: ProposalEffectImage, *, subject: str | None = None
) -> dict:
    """单条效果图的对外形状（不含展示地址）。"""
    attachment = pei.attachment
    product = pei.product
    return {
        "id": str(pei.id),
        "proposal_id": str(pei.proposal_id),
        "project_id": str(pei.project_id) if pei.project_id else None,
        "attachment_id": str(pei.attachment_id),
        "name": pei.name,
        "product_id": str(pei.product_id) if pei.product_id else None,
        "product_no": product.product_no if product else None,
        "product_name": product.product_name if product else None,
        "project_space_id": str(pei.project_space_id) if pei.project_space_id else None,
        "floor_label": pei.floor_label,
        "space_label": pei.space_label,
        "sort": pei.sort,
        "file_name": attachment.file_name if attachment else None,
        "file_type": attachment.file_type if attachment else None,
        "file_size": attachment.file_size if attachment else None,
        "create_time": pei.create_time.isoformat() if pei.create_time else None,
    }


def effect_image_payload(
    pei: ProposalEffectImage, *, subject: str | None = None
) -> dict:
    """对外形状 + 短时展示地址。"""
    data = effect_image_summary(pei, subject=subject)
    data["image_url"] = content_url(pei.attachment_id, subject=subject)
    return data


__all__ = [
    "CONTENT_TOKEN_SCOPE",
    "PREVIEW_EXPIRE_SECONDS",
    "content_url",
    "effect_image_payload",
    "effect_image_summary",
    "load_effect_images",
]