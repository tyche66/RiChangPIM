"""方案效果图 API。

图片本体走既有媒体库：``POST /api/v1/files/upload`` 先落 MinIO 拿到
``attachment_id``，再在本路由绑定到方案。本路由维护「方案 ↔ 附件」的绑定、
展示名与可选的产品/空间归属；删除绑定不会删除媒体库文件。

效果图优先服务方案本身（分享页展示），产品绑定仅是连带回流到产品详情页
「搭配案例」板块：一张效果图可同时绑定一个产品和一个空间（二者独立可空，
也可以都不绑定作为方案整体效果图）。

权限沿用方案域，不新增权限码：
* 读取 ``proposal:view``
* 增删改 ``proposal:edit``

方案确认（confirmed）后仍允许管理效果图：效果图是展示物料，业务上需要在
确认后继续补图 / 换图。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.product import Attachment, Product
from app.models.sales import (
    Proposal,
    ProposalEffectImage,
    ProposalItem,
    ProjectSpace,
)
from app.schemas.proposal_effect_image import (
    ProposalEffectImageBatchCreate,
    ProposalEffectImageCreate,
    ProposalEffectImageUpdate,
)
from app.services.proposal_effect_images import (
    effect_image_payload,
    load_effect_images,
)

router = APIRouter()

# 单方案的效果图上限：与平面图同量级，分享页/产品详情都是贴图展示，20 张足够。
MAX_PROPOSAL_EFFECT_IMAGES = 20


async def _load_proposal(db: AsyncSession, proposal_id: UUID) -> Proposal:
    result = await db.execute(
        select(Proposal).where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "方案不存在"})
    return proposal


async def _load_image_attachment(db: AsyncSession, attachment_id: UUID) -> Attachment:
    attachment = (
        await db.execute(
            select(Attachment).where(
                Attachment.id == attachment_id, Attachment.is_deleted.is_(False)
            )
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})
    if attachment.file_type != "image":
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "效果图仅支持 image 类型的图片附件"}
        )
    return attachment


async def _active_count(db: AsyncSession, proposal_id: UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(ProposalEffectImage)
            .where(
                ProposalEffectImage.proposal_id == proposal_id,
                ProposalEffectImage.is_deleted.is_(False),
            )
        )
    ).scalar_one()


async def _assert_not_bound(db: AsyncSession, proposal_id: UUID, attachment_id: UUID) -> None:
    exists = (
        await db.execute(
            select(ProposalEffectImage.id).where(
                ProposalEffectImage.proposal_id == proposal_id,
                ProposalEffectImage.attachment_id == attachment_id,
                ProposalEffectImage.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "该图片已绑定到此方案，无需重复添加"}
        )


async def _validate_product_binding(
    db: AsyncSession, proposal_id: UUID, product_id: UUID | None
) -> None:
    """校验绑定产品：必须是方案明细中、且产品库中 active 未删除的产品。"""
    if product_id is None:
        return
    in_proposal = (
        await db.execute(
            select(ProposalItem.product_id)
            .where(
                ProposalItem.proposal_id == proposal_id,
                ProposalItem.product_id == product_id,
                ProposalItem.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    active = (
        await db.execute(
            select(Product.id).where(
                Product.id == product_id,
                Product.is_deleted.is_(False),
                Product.status == "active",
            )
        )
    ).scalar_one_or_none()
    if in_proposal is None or active is None:
        raise HTTPException(
            status_code=422,
            detail={"code": 42201, "msg": "效果图只能绑定本方案明细中的启用产品"},
        )


async def _validate_space_binding(
    db: AsyncSession, proposal: Proposal, project_space_id: UUID | None
) -> None:
    """校验空间绑定：空间必须属于方案关联的项目（无项目时不允许绑定）。"""
    if project_space_id is None:
        return
    if proposal.project_id is None:
        raise HTTPException(
            status_code=422,
            detail={"code": 42201, "msg": "方案未关联项目，无法绑定项目空间，可改用楼层/空间名称标签"},
        )
    exists = (
        await db.execute(
            select(ProjectSpace.id).where(
                ProjectSpace.id == project_space_id,
                ProjectSpace.project_id == proposal.project_id,
                ProjectSpace.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=422,
            detail={"code": 42201, "msg": "绑定的空间不属于方案关联的项目"},
        )


async def _validate_bindings(
    db: AsyncSession, proposal: Proposal, product_id: UUID | None, project_space_id: UUID | None
) -> None:
    await _validate_product_binding(db, proposal.id, product_id)
    await _validate_space_binding(db, proposal, project_space_id)


@router.get(
    "",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:view"))],
)
async def list_proposal_effect_images(
    request: Request,
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _load_proposal(db, proposal_id)
    rows = await load_effect_images(db, proposal_id)
    subject = getattr(request.state, "user_id", None)
    return {
        "code": 200,
        "data": {
            "list": [effect_image_payload(row, subject=subject) for row in rows],
            "total": len(rows),
            "limit": MAX_PROPOSAL_EFFECT_IMAGES,
        },
    }


@router.post(
    "",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
@audit_action(
    "proposal_effect_image_create", module="proposals", target_id_kwarg="proposal_id"
)
async def create_proposal_effect_image(
    request: Request,
    proposal_id: UUID,
    data: ProposalEffectImageCreate,
    db: AsyncSession = Depends(get_db),
):
    proposal = await _load_proposal(db, proposal_id)
    await _load_image_attachment(db, data.attachment_id)
    await _assert_not_bound(db, proposal_id, data.attachment_id)
    await _validate_bindings(db, proposal, data.product_id, data.project_space_id)

    if await _active_count(db, proposal_id) >= MAX_PROPOSAL_EFFECT_IMAGES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": f"效果图数量已达上限（每个方案最多 {MAX_PROPOSAL_EFFECT_IMAGES} 张）",
            },
        )

    row = ProposalEffectImage(
        proposal_id=proposal_id,
        project_id=proposal.project_id,
        attachment_id=data.attachment_id,
        name=data.name,
        product_id=data.product_id,
        project_space_id=data.project_space_id,
        floor_label=data.floor_label,
        space_label=data.space_label,
        sort=data.sort,
    )
    db.add(row)
    await db.commit()

    rows = await load_effect_images(db, proposal_id)
    created = next((r for r in rows if r.id == row.id), row)
    return {
        "code": 200,
        "data": effect_image_payload(
            created, subject=getattr(request.state, "user_id", None)
        ),
    }


@router.post(
    "/batch",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
@audit_action(
    "proposal_effect_image_batch_create", module="proposals", target_id_kwarg="proposal_id"
)
async def batch_create_proposal_effect_images(
    request: Request,
    proposal_id: UUID,
    payload: ProposalEffectImageBatchCreate,
    db: AsyncSession = Depends(get_db),
):
    """新增方案对话框用：创建成功后一次性绑定预选的效果图。

    整批要么全部成功要么全部不写：任何一张附件非法就整体 422。
    """
    proposal = await _load_proposal(db, proposal_id)
    items = payload.items

    if len(items) > MAX_PROPOSAL_EFFECT_IMAGES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": f"效果图数量已达上限（每个方案最多 {MAX_PROPOSAL_EFFECT_IMAGES} 张）",
            },
        )

    seen: set[UUID] = set()
    for item in items:
        if item.attachment_id in seen:
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "同一张图片重复提交"}
            )
        seen.add(item.attachment_id)
        await _load_image_attachment(db, item.attachment_id)
        await _assert_not_bound(db, proposal_id, item.attachment_id)
        await _validate_bindings(db, proposal, item.product_id, item.project_space_id)

    if await _active_count(db, proposal_id) + len(items) > MAX_PROPOSAL_EFFECT_IMAGES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": f"效果图数量已达上限（每个方案最多 {MAX_PROPOSAL_EFFECT_IMAGES} 张）",
            },
        )

    for index, item in enumerate(items):
        db.add(
            ProposalEffectImage(
                proposal_id=proposal_id,
                project_id=proposal.project_id,
                attachment_id=item.attachment_id,
                name=item.name,
                product_id=item.product_id,
                project_space_id=item.project_space_id,
                floor_label=item.floor_label,
                space_label=item.space_label,
                sort=item.sort if item.sort else index,
            )
        )
    await db.commit()

    rows = await load_effect_images(db, proposal_id)
    subject = getattr(request.state, "user_id", None)
    return {
        "code": 200,
        "data": {
            "list": [effect_image_payload(row, subject=subject) for row in rows],
            "created": len(items),
            "total": len(rows),
        },
    }


@router.put(
    "/{effect_image_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
@audit_action(
    "proposal_effect_image_update", module="proposals", target_id_kwarg="proposal_id"
)
async def update_proposal_effect_image(
    request: Request,
    proposal_id: UUID,
    effect_image_id: UUID,
    data: ProposalEffectImageUpdate,
    db: AsyncSession = Depends(get_db),
):
    proposal = await _load_proposal(db, proposal_id)
    row = (
        await db.execute(
            select(ProposalEffectImage).where(
                ProposalEffectImage.id == effect_image_id,
                ProposalEffectImage.proposal_id == proposal_id,
                ProposalEffectImage.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "效果图不存在"})

    for field in data.model_fields_set:
        setattr(row, field, getattr(data, field))
    await _validate_bindings(db, proposal, row.product_id, row.project_space_id)
    await db.commit()

    rows = await load_effect_images(db, proposal_id)
    updated = next((r for r in rows if r.id == row.id), row)
    return {
        "code": 200,
        "data": effect_image_payload(
            updated, subject=getattr(request.state, "user_id", None)
        ),
    }


@router.delete(
    "/{effect_image_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
@audit_action(
    "proposal_effect_image_delete", module="proposals", target_id_kwarg="proposal_id"
)
async def delete_proposal_effect_image(
    request: Request,
    proposal_id: UUID,
    effect_image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """只解除绑定，不删除媒体库文件（图片可能还被别的方案引用）。"""
    await _load_proposal(db, proposal_id)
    row = (
        await db.execute(
            select(ProposalEffectImage).where(
                ProposalEffectImage.id == effect_image_id,
                ProposalEffectImage.proposal_id == proposal_id,
                ProposalEffectImage.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "效果图不存在"})

    row.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}