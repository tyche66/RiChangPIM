from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.audit import Share, ShareLog, ShareToken
from app.models.product import Product
from app.models.sales import Proposal, ProposalItem
from app.schemas.stats import HotProductItem, HotProductResponse, ShareStatResponse, TopAccessedItem

router = APIRouter()


def _date_range(start_date: date | None, end_date: date | None):
    start_dt = None
    end_dt = None
    if start_date is not None:
        start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
    if end_date is not None:
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
    return start_dt, end_dt


@router.get("/shares", response_model=dict, dependencies=[Depends(PermissionChecker("stats:view"))])
@audit_action("stats_shares", module="stats")
async def stats_shares(
    request: Request,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    start_dt, end_dt = _date_range(start_date, end_date)

    share_stmt = select(Share).where(Share.is_deleted.is_(False))
    if start_dt is not None:
        share_stmt = share_stmt.where(Share.create_time >= start_dt)
    if end_dt is not None:
        share_stmt = share_stmt.where(Share.create_time <= end_dt)

    total_result = await db.execute(select(func.count()).select_from(share_stmt.subquery()))
    total_shares = total_result.scalar_one()

    active_stmt = share_stmt.where(Share.status == "active")
    active_result = await db.execute(select(func.count()).select_from(active_stmt.subquery()))
    active_shares = active_result.scalar_one()

    log_stmt = select(ShareLog).join(ShareToken, ShareToken.id == ShareLog.share_token_id)
    if start_dt is not None:
        log_stmt = log_stmt.where(ShareLog.access_time >= start_dt)
    if end_dt is not None:
        log_stmt = log_stmt.where(ShareLog.access_time <= end_dt)
    access_result = await db.execute(select(func.count()).select_from(log_stmt.subquery()))
    total_access = access_result.scalar_one()

    top_stmt = (
        select(Share.id, func.count(ShareLog.id).label("access_count"))
        .join(ShareToken, ShareToken.share_id == Share.id)
        .join(ShareLog, ShareLog.share_token_id == ShareToken.id)
        .group_by(Share.id)
        .order_by(func.count(ShareLog.id).desc())
        .limit(10)
    )
    if start_dt is not None:
        top_stmt = top_stmt.where(ShareLog.access_time >= start_dt)
    if end_dt is not None:
        top_stmt = top_stmt.where(ShareLog.access_time <= end_dt)

    top_rows = (await db.execute(top_stmt)).all()
    top_accessed = []
    for share_id, access_count in top_rows:
        proposal_name = None
        share_result = await db.execute(select(Share).where(Share.id == share_id))
        share = share_result.scalar_one_or_none()
        if share and share.share_type == "proposal":
            prop_result = await db.execute(select(Proposal).where(Proposal.id == share.target_id))
            prop = prop_result.scalar_one_or_none()
            if prop:
                proposal_name = prop.proposal_name
        top_accessed.append(
            TopAccessedItem(
                share_id=str(share_id),
                proposal_name=proposal_name,
                access_count=access_count,
            )
        )

    return {
        "code": 200,
        "data": ShareStatResponse(
            total_shares=total_shares,
            total_access=total_access,
            active_shares=active_shares,
            top_accessed=top_accessed,
        ).model_dump(),
    }


@router.get(
    "/products/hot",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("stats:view"))],
)
@audit_action("stats_products_hot", module="stats")
async def stats_products_hot(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    hot_stmt = (
        select(ProposalItem.product_id, func.count(ProposalItem.id).label("ref_count"))
        .group_by(ProposalItem.product_id)
        .order_by(func.count(ProposalItem.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(hot_stmt)).all()

    items = []
    for product_id, ref_count in rows:
        product_result = await db.execute(select(Product).where(Product.id == product_id))
        product = product_result.scalar_one_or_none()
        items.append(
            HotProductItem(
                product_id=product_id,
                product_name=product.product_name if product else None,
                ref_count=ref_count,
            )
        )

    return {
        "code": 200,
        "data": HotProductResponse(items=items).model_dump(),
    }
