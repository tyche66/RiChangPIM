from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.security import create_access_token
from app.middleware.audit import audit_action
from app.models.product import Product, ProductImage
from app.models.project import Project
from app.models.sales import ProjectSpace, Proposal, ProposalFloorPlan, ProposalItem
from app.schemas.proposal import ProposalCreate, ProposalUpdate
from app.services.product_snapshot import build_product_snapshot
from app.services.proposal_floor_plans import floor_plan_payload, load_floor_plans

router = APIRouter()

VALID_STATUSES = {"draft", "confirmed"}


def _round(value: float) -> float:
    return round(float(value), 2)


def _clean_label(value: str | None) -> str | None:
    """Normalize user-entered snapshot labels without inventing a fallback."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _proposal_items_options():
    """Eager-load compatibility space names for proposal item responses."""
    return selectinload(Proposal.items).selectinload(ProposalItem.space).selectinload(
        ProjectSpace.parent
    )


async def _validate_project(project_id: UUID, db: AsyncSession) -> None:
    result = await db.execute(
        select(Project.id).where(Project.id == project_id, Project.is_deleted.is_(False))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=422, detail={"code": 42201, "msg": "关联项目不存在"})


async def _resolve_item_space(
    item,
    project_id: UUID | None,
    db: AsyncSession,
    *,
    ignore_existing_id: bool = False,
) -> dict:
    """Resolve a proposal item's optional space binding and preserve label snapshots.

    Labels are the business-facing facts.  An existing ID is only accepted when it
    belongs to the proposal project; with a project, typed labels create/reuse a
    floor and room node for future back-office maintenance.  Without a project,
    labels remain valid snapshots but no space ID is fabricated.
    """
    floor_label = _clean_label(item.floor_label)
    space_label = _clean_label(item.space_label)
    space_id = None if ignore_existing_id else item.project_space_id

    if project_id is None:
        # Without a project there is no safe scope in which to resolve an ID.
        # Drop it rather than allowing an unscoped/cross-project reference;
        # labels are still valid proposal snapshots.
        return {
            "project_space_id": None,
            "floor_label": floor_label,
            "space_label": space_label,
        }

    await _validate_project(project_id, db)

    bound_space = None
    if space_id is not None:
        bound_space = (
            await db.execute(
                select(ProjectSpace)
                .options(selectinload(ProjectSpace.parent))
                .where(
                    ProjectSpace.id == space_id,
                    ProjectSpace.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if bound_space is None or bound_space.project_id != project_id:
            raise HTTPException(
                status_code=422,
                detail={"code": 42201, "msg": "项目空间不存在或不属于方案关联项目"},
            )

    # A label-only item is enough to create the maintenance nodes.  An existing
    # ID is a compatibility binding, but explicit request labels are authoritative
    # and must resolve to a node in this project rather than keeping a stale node.
    if floor_label or space_label:
        bound_space = None

    if bound_space is None and (floor_label or space_label):
        floor = None
        if floor_label:
            floor = (
                await db.execute(
                    select(ProjectSpace).where(
                        ProjectSpace.project_id == project_id,
                        ProjectSpace.space_type == "floor",
                        ProjectSpace.space_name == floor_label,
                        ProjectSpace.is_deleted.is_(False),
                    )
                )
            ).scalars().first()
            if floor is None:
                floor = ProjectSpace(
                    project_id=project_id,
                    space_type="floor",
                    space_name=floor_label,
                    level=1,
                    sort=0,
                )
                db.add(floor)
                await db.flush()

        if space_label:
            space_query = select(ProjectSpace).where(
                ProjectSpace.project_id == project_id,
                ProjectSpace.space_type.in_(("room", "zone", "other")),
                ProjectSpace.space_name == space_label,
                ProjectSpace.is_deleted.is_(False),
            )
            if floor is not None:
                space_query = space_query.where(ProjectSpace.parent_id == floor.id)
            else:
                space_query = space_query.where(ProjectSpace.parent_id.is_(None))
            bound_space = (await db.execute(space_query)).scalars().first()
            if bound_space is None:
                bound_space = ProjectSpace(
                    project_id=project_id,
                    parent_id=floor.id if floor is not None else None,
                    space_type="room" if floor is not None else "other",
                    space_name=space_label,
                    level=2 if floor is not None else 1,
                    sort=0,
                )
                db.add(bound_space)
                await db.flush()
        elif floor is not None:
            bound_space = floor

    if bound_space is not None:
        space_id = bound_space.id
        if floor_label is None:
            if bound_space.space_type == "floor":
                floor_label = bound_space.space_name
            else:
                parent = getattr(bound_space, "parent", None)
                if parent is not None and parent.space_type == "floor":
                    floor_label = parent.space_name
        if space_label is None and bound_space.space_type != "floor":
            space_label = bound_space.space_name

    return {
        "project_space_id": space_id,
        "floor_label": floor_label,
        "space_label": space_label,
    }


async def _resolve_project_spaces(
    items,
    project_id: UUID | None,
    db: AsyncSession,
    *,
    ignore_existing_ids: bool = False,
) -> list[dict]:
    """Resolve every item before mutating proposal rows."""
    return [
        await _resolve_item_space(
            item,
            project_id,
            db,
            ignore_existing_id=ignore_existing_ids,
        )
        for item in items
    ]


async def _validate_proposal_items(item_ids: list[UUID], db: AsyncSession) -> dict[UUID, Product]:
    """校验产品存在、未删除、status=active，并返回去重后的产品映射。"""
    seen: set[UUID] = set()
    for pid in item_ids:
        if pid in seen:
            raise HTTPException(status_code=422, detail={"code": 42201, "msg": f"重复产品 {pid}"})
        seen.add(pid)

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.category))
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
            select(ProductImage.product_id, ProductImage.attachment_id).where(
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
            token_type="file_content",
        )
        urls[product_id] = f"/api/v1/files/{attachment_id}/content?token={token}"
    return urls


def _enrich_item(item: ProposalItem, product: Product | None, cover_url: str | None) -> dict:
    snapshot = item.product_snapshot
    snapshot_face_price = snapshot.get("face_price") if snapshot else None
    fp = (
        snapshot_face_price
        if snapshot_face_price not in (None, "")
        else (product.face_price if product else 0.0)
    )
    floor_label = item.floor_label
    space_label = item.space_label
    bound_space = item.__dict__.get("space")
    if bound_space is not None:
        if floor_label is None:
            if bound_space.space_type == "floor":
                floor_label = bound_space.space_name
            else:
                parent = getattr(bound_space, "parent", None)
                if parent is not None and parent.space_type == "floor":
                    floor_label = parent.space_name
        if space_label is None and bound_space.space_type != "floor":
            space_label = bound_space.space_name
    # 展示字段按"快照优先、当前产品其次、缺失文案兜底"合并
    return {
        "id": str(item.id),
        "product_id": str(item.product_id),
        "product_no": (
            snapshot.get("product_no") if snapshot else None
        ) or (product.product_no if product else None),
        "product_name": (
            snapshot.get("product_name") if snapshot else None
        ) or (product.product_name if product else None),
        "category_name": (
            snapshot.get("category_name") if snapshot else None
        ) or (product.category.category_name if product and product.category else None),
        "material": (snapshot.get("material") if snapshot else None)
        or (product.material if product else None),
        "colors": (snapshot.get("colors") if snapshot else None)
        or (product.colors if product else None),
        "material_description": (
            (snapshot.get("material_description") if snapshot else None)
            or (product.material_description if product else None)
        ),
        "specification": (snapshot.get("specification") if snapshot else None)
        or (product.specification if product else None),
        "face_price": fp,
        "quantity": item.quantity,
        "remark": item.remark,
        "line_total": _round(fp * item.quantity),
        "cover_image_url": cover_url,
        # Track C：空间与快照
        "project_space_id": str(item.project_space_id) if item.project_space_id else None,
        "floor_label": floor_label,
        "space_label": space_label,
        "material_desc": item.material_desc,
        "product_snapshot": snapshot,
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
        "customer_id": str(proposal.customer_id) if proposal.customer_id else None,
        "project_id": str(proposal.project_id) if proposal.project_id else None,
        "creator_id": str(proposal.creator_id),
        "status": proposal.status,
        "ai_polished": proposal.ai_polished,
        "ai_polish_content": proposal.ai_polish_content,
        "ai_polish_at": _iso(proposal.ai_polish_at),
        "ai_polish_model": proposal.ai_polish_model,
        "ai_generation_version": proposal.ai_generation_version,
        "ai_source_ids": proposal.ai_source_ids,
        "ai_confirmed_by": str(proposal.ai_confirmed_by) if proposal.ai_confirmed_by else None,
        "total_face_value": proposal.total_face_value,
        "create_time": _iso(proposal.create_time),
    }


async def _floor_plan_payloads(
    db: AsyncSession, proposal_id: UUID, request: Request
) -> list[dict]:
    """方案详情里的平面图：短时展示地址按当前登录用户签发。"""
    rows = await load_floor_plans(db, proposal_id)
    subject = getattr(request.state, "user_id", None)
    return [floor_plan_payload(row, subject=subject) for row in rows]


def _wrap_proposal(
    proposal: Proposal, enriched_items: list[dict], floor_plans: list[dict] | None = None
) -> dict:
    resp = _proposal_to_dict(proposal)
    resp["items"] = enriched_items
    # Track D：平面图随详情返回，前端不必为只读展示再打一次接口
    resp["floor_plans"] = floor_plans or []
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
        select(Proposal).options(selectinload(Proposal.items)).where(Proposal.is_deleted.is_(False))
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
            raise HTTPException(status_code=422, detail={"code": 42201, "msg": "非法状态值"})
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
async def get_proposal(request: Request, proposal_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Proposal)
        .options(_proposal_items_options())
        .where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "方案不存在"})

    product_ids = [it.product_id for it in proposal.items]
    prod_map: dict[UUID, Product] = {}
    if product_ids:
        prod_result = await db.execute(
            select(Product)
                .options(selectinload(Product.category))
                .where(Product.id.in_(product_ids), Product.is_deleted.is_(False))
        )
        prod_map = {p.id: p for p in prod_result.scalars().all()}

    cover_urls = await _cover_urls(product_ids, request, db)
    enriched_items = []
    for it in proposal.items:
        prod = prod_map.get(it.product_id)
        enriched_items.append(_enrich_item(it, prod, cover_urls.get(it.product_id)))

    floor_plans = await _floor_plan_payloads(db, proposal.id, request)
    return _wrap_proposal(proposal, enriched_items, floor_plans)


@router.post(
    "",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("proposal:create"))],
)
async def create_proposal(
    request: Request, proposal_data: ProposalCreate, db: AsyncSession = Depends(get_db)
):
    products = await _validate_proposal_items([i.product_id for i in proposal_data.items], db)
    resolved_spaces = await _resolve_project_spaces(
        proposal_data.items, proposal_data.project_id, db
    )

    proposal = Proposal(
        proposal_no=f"PR-2026-{str(uuid4())[:8].upper()}",
        proposal_name=proposal_data.proposal_name,
        creator_id=proposal_data.creator_id,
        customer_name=proposal_data.customer_name,
        customer_id=proposal_data.customer_id,
        project_id=proposal_data.project_id,
    )
    db.add(proposal)
    await db.flush()

    items = []
    for item_data, space_data in zip(proposal_data.items, resolved_spaces, strict=True):
        prod = products[item_data.product_id]
        # 服务端生成快照，绝不信任前端传入的产品事实
        snapshot = await build_product_snapshot(db, item_data.product_id)
        item = ProposalItem(
            proposal_id=proposal.id,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            remark=item_data.remark,
            project_space_id=space_data["project_space_id"],
            floor_label=space_data["floor_label"],
            space_label=space_data["space_label"],
            material_desc=item_data.material_desc,
            product_snapshot=snapshot,
        )
        db.add(item)
        items.append((item, prod))
    proposal.total_face_value = _round(sum(prod.face_price * it.quantity for it, prod in items))

    await db.commit()
    result = await db.execute(
        select(Proposal).options(_proposal_items_options()).where(Proposal.id == proposal.id)
    )
    prop = result.scalar_one()

    prod_map = {p.id: p for _, p in items}
    cover_urls = await _cover_urls([item.product_id for item in prop.items], request, db)
    enriched = []
    for it in prop.items:
        prod = prod_map.get(it.product_id)
        enriched.append(_enrich_item(it, prod, cover_urls.get(it.product_id)))

    return _wrap_proposal(prop, enriched, [])


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
        raise HTTPException(status_code=422, detail={"code": 42201, "msg": "方案已确认，不可修改"})

    items_prod_map: dict[UUID, Product] = {}
    update_fields = set(proposal_data.model_fields_set) - {"items"}
    project_changed_without_items = (
        "project_id" in proposal_data.model_fields_set
        and "items" not in proposal_data.model_fields_set
    )
    if project_changed_without_items:
        resolved_spaces = await _resolve_project_spaces(
            proposal.items,
            proposal_data.project_id,
            db,
            # Existing item IDs belong to the old project.  On a project move,
            # only the saved labels may be used to create bindings in the new
            # project; never carry an old-project FK across the boundary.
            ignore_existing_ids=proposal.project_id != proposal_data.project_id,
        )
        for existing_item, space_data in zip(proposal.items, resolved_spaces, strict=True):
            existing_item.project_space_id = space_data["project_space_id"]
            existing_item.floor_label = space_data["floor_label"]
            existing_item.space_label = space_data["space_label"]
    for field in update_fields:
        setattr(proposal, field, getattr(proposal_data, field))

    if "project_id" in update_fields:
        # Track D：平面图的项目归属跟随方案，避免方案换项目后平面图仍挂在旧项目
        await db.execute(
            sa_update(ProposalFloorPlan)
            .where(
                ProposalFloorPlan.proposal_id == proposal.id,
                ProposalFloorPlan.is_deleted.is_(False),
            )
            .values(project_id=proposal.project_id)
        )

    if "items" in proposal_data.model_fields_set:
        new_items = proposal_data.items
        if new_items is None or not new_items:
            raise HTTPException(status_code=422, detail={"code": 42201, "msg": "方案明细不可为空"})
        effective_project_id = (
            proposal_data.project_id
            if "project_id" in proposal_data.model_fields_set
            else proposal.project_id
        )
        products = await _validate_proposal_items([i.product_id for i in new_items], db)
        resolved_spaces = await _resolve_project_spaces(new_items, effective_project_id, db)
        # Replace through the loaded relationship collection.  The session uses
        # expire_on_commit=False, so assigning an unrelated list here would leave
        # proposal.items stale after commit and selectinload() would not
        # repopulate an already-loaded collection.  Clearing also lets the
        # delete-orphan cascade remove the old rows in the same transaction.
        proposal.items.clear()
        created = []
        for item_data, space_data in zip(new_items, resolved_spaces, strict=True):
            prod = products[item_data.product_id]
            snapshot = await build_product_snapshot(db, item_data.product_id)
            item = ProposalItem(
                product_id=item_data.product_id,
                quantity=item_data.quantity,
                remark=item_data.remark,
                project_space_id=space_data["project_space_id"],
                floor_label=space_data["floor_label"],
                space_label=space_data["space_label"],
                material_desc=item_data.material_desc,
                product_snapshot=snapshot,
            )
            proposal.items.append(item)
            created.append((item, prod))

        total_face = _round(sum(prod.face_price * it.quantity for it, prod in created))
        proposal.total_face_value = total_face
        items_prod_map = {p.id: p for _, p in created}

    await db.commit()
    result = await db.execute(
        select(Proposal)
        .options(_proposal_items_options())
        .where(Proposal.id == proposal.id)
        # The Proposal instance survives commit (expire_on_commit=False);
        # force a refresh so the response reflects the committed item graph.
        .execution_options(populate_existing=True)
    )
    proposal = result.scalar_one()

    # 富化返回 item 详情
    if not items_prod_map and proposal.items:
        product_result = await db.execute(
            select(Product)
                .options(selectinload(Product.category))
                .where(
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

    floor_plans = await _floor_plan_payloads(db, proposal.id, request)
    return _wrap_proposal(proposal, enriched, floor_plans)


@router.post(
    "/{proposal_id}/confirm",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("proposal:confirm"))],
)
@audit_action("proposal_confirm", module="proposals", target_id_kwarg="proposal_id")
async def confirm_proposal(request: Request, proposal_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Proposal)
        .options(_proposal_items_options())
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
    result = await db.execute(
        select(Proposal)
        .options(_proposal_items_options())
        .where(Proposal.id == proposal.id)
    )
    proposal = result.scalar_one()
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
        .options(_proposal_items_options())
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
                select(Product)
                .options(selectinload(Product.category))
                .where(Product.id.in_(product_ids), Product.is_deleted.is_(False))
            )
            prod_map = {p.id: p for p in prod_result.scalars().all()}
        cover_urls = await _cover_urls(product_ids, request, db)
        enriched = []
        for it in proposal.items:
            enriched.append(
                _enrich_item(it, prod_map.get(it.product_id), cover_urls.get(it.product_id))
            )
        return _wrap_proposal(
            proposal, enriched, await _floor_plan_payloads(db, proposal.id, request)
        )

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
    result = await db.execute(
        select(Proposal)
        .options(_proposal_items_options())
        .where(Proposal.id == proposal.id)
    )
    proposal = result.scalar_one()

    product_ids = [it.product_id for it in proposal.items]
    prod_map: dict[UUID, Product] = {}
    if product_ids:
        prod_result = await db.execute(
            select(Product)
                .options(selectinload(Product.category))
                .where(Product.id.in_(product_ids), Product.is_deleted.is_(False))
        )
        prod_map = {p.id: p for p in prod_result.scalars().all()}
    cover_urls = await _cover_urls(product_ids, request, db)
    enriched = []
    for it in proposal.items:
        enriched.append(
            _enrich_item(it, prod_map.get(it.product_id), cover_urls.get(it.product_id))
        )
    floor_plans = await _floor_plan_payloads(db, proposal.id, request)
    return _wrap_proposal(proposal, enriched, floor_plans)


@router.delete("/{proposal_id}", dependencies=[Depends(PermissionChecker("proposal:delete"))])
@audit_action("proposal_delete", module="proposals")
async def delete_proposal(request: Request, proposal_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Proposal)
        .options(_proposal_items_options())
        .where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "方案不存在"})

    proposal.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}
