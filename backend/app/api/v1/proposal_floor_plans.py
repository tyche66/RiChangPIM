"""方案平面图 API（Track D）。

图片本体走既有媒体库：``POST /api/v1/files/upload`` 先落 MinIO 拿到
``attachment_id``，再在本路由绑定到方案。本路由只维护「方案 ↔ 附件」的
绑定与展示名，删除绑定不会删除媒体库文件。

权限沿用方案域，不新增权限码：
* 读取 ``proposal:view``
* 增删改 ``proposal:edit``

方案确认（confirmed）后仍允许管理平面图：平面图是展示物料，不是价格与
明细事实，业务上需要在确认后继续补图 / 换图。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.product import Attachment
from app.models.sales import Proposal, ProposalFloorPlan
from app.schemas.proposal_floor_plan import (
    ProposalFloorPlanBatchCreate,
    ProposalFloorPlanCreate,
    ProposalFloorPlanUpdate,
)
from app.services.proposal_floor_plans import (
    floor_plan_payload,
    load_floor_plans,
)

router = APIRouter()

# 单个方案的平面图上限。与场景图（产品 30 张）同量级，取更保守的 20 张：
# 分享页右侧栏是缩略图入口，再多也不会同屏展示，只会拖慢一次页面加载。
MAX_PROPOSAL_FLOOR_PLANS = 20


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
            status_code=422, detail={"code": 42201, "msg": "平面图仅支持 image 类型的图片附件"}
        )
    return attachment


async def _active_count(db: AsyncSession, proposal_id: UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(ProposalFloorPlan)
            .where(
                ProposalFloorPlan.proposal_id == proposal_id,
                ProposalFloorPlan.is_deleted.is_(False),
            )
        )
    ).scalar_one()


async def _assert_not_bound(db: AsyncSession, proposal_id: UUID, attachment_id: UUID) -> None:
    exists = (
        await db.execute(
            select(ProposalFloorPlan.id).where(
                ProposalFloorPlan.proposal_id == proposal_id,
                ProposalFloorPlan.attachment_id == attachment_id,
                ProposalFloorPlan.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "该图片已绑定到此方案，无需重复添加"}
        )


@router.get(
    "",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:view"))],
)
async def list_proposal_floor_plans(
    request: Request,
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _load_proposal(db, proposal_id)
    rows = await load_floor_plans(db, proposal_id)
    subject = getattr(request.state, "user_id", None)
    return {
        "code": 200,
        "data": {
            "list": [floor_plan_payload(row, subject=subject) for row in rows],
            "total": len(rows),
            "limit": MAX_PROPOSAL_FLOOR_PLANS,
        },
    }


@router.post(
    "",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
@audit_action(
    "proposal_floor_plan_create", module="proposals", target_id_kwarg="proposal_id"
)
async def create_proposal_floor_plan(
    request: Request,
    proposal_id: UUID,
    data: ProposalFloorPlanCreate,
    db: AsyncSession = Depends(get_db),
):
    proposal = await _load_proposal(db, proposal_id)
    await _load_image_attachment(db, data.attachment_id)
    await _assert_not_bound(db, proposal_id, data.attachment_id)

    if await _active_count(db, proposal_id) >= MAX_PROPOSAL_FLOOR_PLANS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": f"平面图数量已达上限（每个方案最多 {MAX_PROPOSAL_FLOOR_PLANS} 张）",
            },
        )

    row = ProposalFloorPlan(
        proposal_id=proposal_id,
        project_id=proposal.project_id,
        attachment_id=data.attachment_id,
        name=data.name,
        floor_label=data.floor_label,
        space_label=data.space_label,
        sort=data.sort,
    )
    db.add(row)
    await db.commit()

    rows = await load_floor_plans(db, proposal_id)
    created = next((r for r in rows if r.id == row.id), row)
    return {
        "code": 200,
        "data": floor_plan_payload(
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
    "proposal_floor_plan_batch_create", module="proposals", target_id_kwarg="proposal_id"
)
async def batch_create_proposal_floor_plans(
    request: Request,
    proposal_id: UUID,
    payload: ProposalFloorPlanBatchCreate,
    db: AsyncSession = Depends(get_db),
):
    """新增方案对话框用：创建成功后一次性绑定预选的平面图。

    整批要么全部成功要么全部不写：任何一张附件非法就整体 422，避免用户看到
    「只进去一半」的对话框结果而无法判断是否要重试。
    """
    proposal = await _load_proposal(db, proposal_id)
    items = payload.items

    if len(items) > MAX_PROPOSAL_FLOOR_PLANS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": f"平面图数量已达上限（每个方案最多 {MAX_PROPOSAL_FLOOR_PLANS} 张）",
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

    if await _active_count(db, proposal_id) + len(items) > MAX_PROPOSAL_FLOOR_PLANS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": f"平面图数量已达上限（每个方案最多 {MAX_PROPOSAL_FLOOR_PLANS} 张）",
            },
        )

    for index, item in enumerate(items):
        db.add(
            ProposalFloorPlan(
                proposal_id=proposal_id,
                project_id=proposal.project_id,
                attachment_id=item.attachment_id,
                name=item.name,
                floor_label=item.floor_label,
                space_label=item.space_label,
                sort=item.sort if item.sort else index,
            )
        )
    await db.commit()

    rows = await load_floor_plans(db, proposal_id)
    subject = getattr(request.state, "user_id", None)
    return {
        "code": 200,
        "data": {
            "list": [floor_plan_payload(row, subject=subject) for row in rows],
            "created": len(items),
            "total": len(rows),
        },
    }


@router.put(
    "/{floor_plan_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
@audit_action(
    "proposal_floor_plan_update", module="proposals", target_id_kwarg="proposal_id"
)
async def update_proposal_floor_plan(
    request: Request,
    proposal_id: UUID,
    floor_plan_id: UUID,
    data: ProposalFloorPlanUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _load_proposal(db, proposal_id)
    row = (
        await db.execute(
            select(ProposalFloorPlan).where(
                ProposalFloorPlan.id == floor_plan_id,
                ProposalFloorPlan.proposal_id == proposal_id,
                ProposalFloorPlan.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "平面图不存在"})

    for field in data.model_fields_set:
        setattr(row, field, getattr(data, field))
    await db.commit()

    rows = await load_floor_plans(db, proposal_id)
    updated = next((r for r in rows if r.id == row.id), row)
    return {
        "code": 200,
        "data": floor_plan_payload(
            updated, subject=getattr(request.state, "user_id", None)
        ),
    }


@router.delete(
    "/{floor_plan_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
@audit_action(
    "proposal_floor_plan_delete", module="proposals", target_id_kwarg="proposal_id"
)
async def delete_proposal_floor_plan(
    request: Request,
    proposal_id: UUID,
    floor_plan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """只解除绑定，不删除媒体库文件（图片可能还被别的方案引用）。"""
    await _load_proposal(db, proposal_id)
    row = (
        await db.execute(
            select(ProposalFloorPlan).where(
                ProposalFloorPlan.id == floor_plan_id,
                ProposalFloorPlan.proposal_id == proposal_id,
                ProposalFloorPlan.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "平面图不存在"})

    row.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}
