from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.security import create_access_token
from app.middleware.audit import audit_action
from app.models.product import Product, ProductImage
from app.models.sales import Proposal, ProposalItem
from app.schemas.proposal import ProposalCreate, ProposalResponse, ProposalUpdate

router = APIRouter()

VALID_STATUSES = {"draft", "confirmed"}


def _round(value: float) -> float:
    return round(float(value), 2)


async def _validate_proposal_items(
    item_ids: list[UUID], db: AsyncSession
) -> dict[UUID, Product]:
    """校验产品存在、未删除、status=active，并返回去重后的产品映射。"""
    seen: set[UUID] = set()
    for pid in item_ids:
        if pid in seen:
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": f"重复产品 {pid}"}
            )
        seen.add(pid)

    result = await db.execute(
        select(Product)
        .where(
            Product.id.in_(item_ids),
            Product.is_deleted.is_(False),
            Product.status == "active",
        )
    )
    found = {p.id: p for p in result.scalars().all()}

    missing = set(item_ids) - set(found)
    if missing:
        ids = ",".join(str(m) for m in missing)
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": f"产品不存在或非激活: {ids}"}
        )
    return found


async def _cover_urls(
    product_ids: list[UUID], request: Request, db: AsyncSession
) -> dict[UUID, str]:
    if not product_ids:
        return {}
    rows = (
        await db.execute(
            select(ProductImage.product_id, ProductImage.attachment_id)
            .where(
                ProductImage.product_id.in_(product_ids),
                ProductImage.is_deleted.is_(False),
                ProductImage.is_cover.is_(True),
            )
        )
    ).all()
    urls = {}
    for product_id, attachment_id in rows:
        if not attachment_id:
            continue
        token = create_access_token(
            {
                "sub": getattr(request.state, "user_id", None) or "file-content",
                "scope": "file_content",
                "attachment_id": str(attachment_id),
            },
            expires_delta=timedelta(minutes=15),
        )
        urls[product_id] = f"/api/v1/files/{attachment_id}/content?token={token}"
    return urls


def _enrich_item(item: ProposalItem, product: Product | None, cover_url: str | None) -> dict:
    fp = product.face_price if product else 0.0
    return {
        "id": str(item.id),
        "product_id": str(item.product_id),
        "product_no": product.product_no if product else None,
        "product_name": product.product_name if product else None,
        "face_price": fp,
        "quantity": item.quantity,
        "remark": item.remark,
        "line_total": _round(fp * item.quantity),
        "cover_image_url": cover_url,
    }


def _proposal_to_dict(proposal: Proposal) -> dict:
    """Serialize proposal ORM object to dict (items field omitted; caller enriches)."""
    from datetime import datetime

    def _iso(v):
        return v.isoformat() if isinstance(v, datetime) else v

    return {
        "id": str(proposal.id),
        "proposal_no": proposal.proposal_no,
        "proposal_name": proposal.proposal_name,
        "customer_name": proposal.customer_name,
        "creator_id": str(proposal.creator_id),
        "status": proposal.status,
        "ai_polished": proposal.ai_polished,
        "ai_polish_content": proposal.ai_polish_content,
        "ai_polish_at": _iso(proposal.ai_polish_at),
        "ai_polish_model": proposal.ai_polish_model,
        "total_face_value": proposal.total_face_value,
        "create_time": _iso(proposal.create_time),
    }


def _wrap_proposal(proposal: Proposal, enriched_items: list[dict]) -> dict:
    resp = _proposal_to_dict(proposal)
    resp["items"] = enriched_items
    return {"code": 200, "data": resp}


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("proposal:view"))])
async def list_proposals(
    keyword: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Proposal)
        .options(selectinload(Proposal.items))
        .where(Proposal.is_deleted.is_(False))
    )
    if keyword is not None:
        kw = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Proposal.proposal_name.ilike(kw),
                Proposal.customer_name.ilike(kw),
                Proposal.proposal_no.ilike(kw),
            )
        )
    if status is not None:
        if status not in VALID_STATUSES:
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "非法状态值"}
            )
        stmt = stmt.where(Proposal.status == status)

    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()

    stmt = stmt.order_by(Proposal.create_time.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    proposals = result.scalars().all()
    return {
        "code": 200,
        "data": {
            "list": [_proposal_to_dict(p) for p in proposals],
            "total": total,
            "page": page,
            "size": size,
        },
    }


@router.get(
    "/{proposal_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:view"))],
)
async def get_proposal(
    request: Request, proposal_id: UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Proposal)
        .options(selectinload(Proposal.items))
        .where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "方案不存在"})

    product_ids = [it.product_id for it in proposal.items]
    prod_map: dict[UUID, Product] = {}
    if product_ids:
        prod_result = await db.execute(
            select(Product).where(
                Product.id.in_(product_ids), Product.is_deleted.is_(False)
            )
        )
        prod_map = {p.id: p for p in prod_result.scalars().all()}

    cover_urls = await _cover_urls(product_ids, request, db)
    enriched_items = []
    for it in proposal.items:
        prod = prod_map.get(it.product_id)
        enriched_items.append(_enrich_item(it, prod, cover_urls.get(it.product_id)))

    return _wrap_proposal(proposal, enriched_items)


@router.post(
    "",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("proposal:create"))],
)
async def create_proposal(
    request: Request, proposal_data: ProposalCreate, db: AsyncSession = Depends(get_db)
):
    products = await _validate_proposal_items(
        [i.product_id for i in proposal_data.items], db
    )

    proposal = Proposal(
        proposal_no=f"PR-2026-{str(uuid4())[:8].upper()}",
        proposal_name=proposal_data.proposal_name,
        creator_id=proposal_data.creator_id,
        customer_name=proposal_data.customer_name,
    )
    db.add(proposal)
    await db.flush()

    items = []
    for item_data in proposal_data.items:
        prod = products[item_data.product_id]
        item = ProposalItem(
            proposal_id=proposal.id,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            remark=item_data.remark,
        )
        db.add(item)
        items.append((item, prod))
    proposal.total_face_value = _round(
        sum(prod.face_price * it.quantity for it, prod in items)
    )

    await db.commit()
    result = await db.execute(
        select(Proposal).options(selectinload(Proposal.items)).where(Proposal.id == proposal.id)
    )
    prop = result.scalar_one()

    prod_map = {p.id: p for _, p in items}
    cover_urls = await _cover_urls([item.product_id for item in prop.items], request, db)
    enriched = []
    for it in prop.items:
        prod = prod_map.get(it.product_id)
        enriched.append(_enrich_item(it, prod, cover_urls.get(it.product_id)))

    return _wrap_proposal(prop, enriched)


@router.put(
    "/{proposal_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
async def update_proposal(
    request: Request,
    proposal_id: UUID,
    proposal_data: ProposalUpdate,
    db: AsyncSession = Depends(get_db),
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
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "方案已确认，不可修改"}
        )

    items_prod_map: dict[UUID, Product] = {}
    update_fields = set(proposal_data.model_fields_set) - {"items"}
    for field in update_fields:
        setattr(proposal, field, getattr(proposal_data, field))

    if "items" in proposal_data.model_fields_set:
        new_items = proposal_data.items
        if new_items is None or not new_items:
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "方案明细不可为空"}
            )
        products = await _validate_proposal_items(
            [i.product_id for i in new_items], db
        )
        old_items = await db.execute(
            select(ProposalItem).where(ProposalItem.proposal_id == proposal.id)
        )
        for old in old_items.scalars().all():
            await db.delete(old)
        proposal.items = []
        created = []
        for item_data in new_items:
            prod = products[item_data.product_id]
            item = ProposalItem(
                proposal_id=proposal.id,
                product_id=item_data.product_id,
                quantity=item_data.quantity,
                remark=item_data.remark,
            )
            db.add(item)
            created.append((item, prod))

        total_face = _round(
            sum(prod.face_price * it.quantity for it, prod in created)
        )
        proposal.total_face_value = total_face
        items_prod_map = {p.id: p for _, p in created}

    await db.commit()
    await db.refresh(proposal)
    await db.refresh(proposal, ["items"])

    # 富化返回 item 详情
    if not items_prod_map and proposal.items:
        product_result = await db.execute(
            select(Product).where(
                Product.id.in_([item.product_id for item in proposal.items]),
                Product.is_deleted.is_(False),
            )
        )
        items_prod_map = {product.id: product for product in product_result.scalars().all()}
    cover_urls = await _cover_urls([item.product_id for item in proposal.items], request, db)
    enriched = []
    for it in proposal.items:
        enriched.append(
            _enrich_item(it, items_prod_map.get(it.product_id), cover_urls.get(it.product_id))
        )

    return _wrap_proposal(proposal, enriched)


@router.post(
    "/{proposal_id}/confirm",
    response_model=dict,
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
        return _wrap_proposal(proposal, [])
    if not proposal.items:
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "方案明细为空，不可确认"}
        )

    proposal.status = "confirmed"
    await db.commit()
    await db.refresh(proposal)
    await db.refresh(proposal, ["items"])
    return _wrap_proposal(proposal, [])


@router.post(
    "/{proposal_id}/revert-confirmation",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:edit"))],
)
@audit_action("proposal_revert_confirmation", module="proposals", target_id_kwarg="proposal_id")
async def revert_confirmation(
    request: Request, proposal_id: UUID, db: AsyncSession = Depends(get_db)
):
    """确认方案回退到草稿：confirmed -> draft，幂等，返回完整富化 items。"""
    result = await db.execute(
        select(Proposal)
        .options(selectinload(Proposal.items))
        .where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "方案不存在"})

    # 幂等：已处于草稿直接返回富化结果
    if proposal.status == "draft":
        product_ids = [it.product_id for it in proposal.items]
        prod_map: dict[UUID, Product] = {}
        if product_ids:
            prod_result = await db.execute(
                select(Product).where(
                    Product.id.in_(product_ids), Product.is_deleted.is_(False)
                )
            )
            prod_map = {p.id: p for p in prod_result.scalars().all()}
        cover_urls = await _cover_urls(product_ids, request, db)
        enriched = []
        for it in proposal.items:
            enriched.append(_enrich_item(it, prod_map.get(it.product_id), cover_urls.get(it.product_id)))
        return _wrap_proposal(proposal, enriched)

    if proposal.status != "confirmed":
        raise HTTPException(
            status_code=422,
            detail={"code": 42201, "msg": f"方案状态为 {proposal.status}，无法撤销确认"},
        )

    # 存在未删除的 confirmed quotation 则阻止
    from app.models.sales import Quotation

    confirmed_qt_count = (
        await db.execute(
            select(func.count()).where(
                Quotation.proposal_id == proposal.id,
                Quotation.status == "confirmed",
                Quotation.is_deleted.is_(False),
            )
        )
    ).scalar_one()
    if confirmed_qt_count > 0:
        raise HTTPException(
            status_code=422,
            detail={"code": 42201, "msg": "方案存在已确认的报价单，不可撤销确认"},
        )

    proposal.status = "draft"
    await db.commit()
    await db.refresh(proposal)
    await db.refresh(proposal, ["items"])

    product_ids = [it.product_id for it in proposal.items]
    prod_map: dict[UUID, Product] = {}
    if product_ids:
        prod_result = await db.execute(
            select(Product).where(
                Product.id.in_(product_ids), Product.is_deleted.is_(False)
            )
        )
        prod_map = {p.id: p for p in prod_result.scalars().all()}
    cover_urls = await _cover_urls(product_ids, request, db)
    enriched = []
    for it in proposal.items:
        enriched.append(_enrich_item(it, prod_map.get(it.product_id), cover_urls.get(it.product_id)))
    return _wrap_proposal(proposal, enriched)


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
