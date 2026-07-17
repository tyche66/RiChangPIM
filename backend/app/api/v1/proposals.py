from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.sales import Proposal, ProposalItem
from app.schemas.proposal import ProposalCreate, ProposalResponse, ProposalUpdate

router = APIRouter()


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("proposal:view"))])
async def list_proposals(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Proposal)
        .options(selectinload(Proposal.items))
        .where(Proposal.is_deleted.is_(False)))
    proposals = result.scalars().all()
    return {"code": 200, "data": {"list": [ProposalResponse.model_validate(p) for p in proposals]}}


@router.get(
    "/{proposal_id}",
    response_model=ProposalResponse,
    dependencies=[Depends(PermissionChecker("proposal:view"))],
)
async def get_proposal(proposal_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Proposal)
        .options(selectinload(Proposal.items))
        .where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "方案不存在"})
    return proposal


@router.post(
    "",
    response_model=ProposalResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker("proposal:create"))],
)
async def create_proposal(proposal_data: ProposalCreate, db: AsyncSession = Depends(get_db)):
    proposal = Proposal(
        proposal_no=f"PR-2026-{str(uuid4())[:8].upper()}",
        proposal_name=proposal_data.proposal_name,
        creator_id=proposal_data.creator_id,
        customer_name=proposal_data.customer_name,
    )
    db.add(proposal)
    await db.flush()

    for item_data in proposal_data.items:
        item = ProposalItem(
            proposal_id=proposal.id,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            remark=item_data.remark,
        )
        db.add(item)

    await db.commit()
    result = await db.execute(
        select(Proposal).options(selectinload(Proposal.items)).where(Proposal.id == proposal.id)
    )
    return result.scalar_one()


@router.put(
    "/{proposal_id}",
    response_model=ProposalResponse,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
async def update_proposal(
    proposal_id: UUID, proposal_data: ProposalUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Proposal)
        .options(selectinload(Proposal.items))
        .where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "方案不存在"})

    if proposal.status == "confirmed":
        raise HTTPException(status_code=422, detail={"code": 42201, "msg": "方案已确认，不可修改"})

    proposal.proposal_name = proposal_data.proposal_name
    proposal.customer_name = proposal_data.customer_name
    await db.commit()
    await db.refresh(proposal)
    return proposal


@router.post(
    "/{proposal_id}/confirm",
    response_model=ProposalResponse,
    dependencies=[Depends(PermissionChecker("proposal:confirm"))],
)
@audit_action("proposal_confirm", module="proposals", target_id_kwarg="proposal_id")
async def confirm_proposal(request: Request, proposal_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Proposal)
        .options(selectinload(Proposal.items))
        .where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "方案不存在"})
    if proposal.status == "confirmed":
        return proposal

    proposal.status = "confirmed"
    await db.commit()
    await db.refresh(proposal)
    return proposal


@router.delete("/{proposal_id}", dependencies=[Depends(PermissionChecker("proposal:delete"))])
@audit_action("proposal_delete", module="proposals")
async def delete_proposal(request: Request, proposal_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Proposal)
        .options(selectinload(Proposal.items))
        .where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "方案不存在"})

    proposal.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}
