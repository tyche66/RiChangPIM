from datetime import UTC, datetime, timedelta
from html import escape
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.security import create_access_token
from app.middleware.audit import audit_action
from app.models.product import Product, ProductImage
from app.models.sales import Proposal, Quotation, QuotationItem
from app.schemas.quotation import (
    QuotationCreate,
    QuotationResponse,
    QuotationUpdate,
)

router = APIRouter()

VALID_STATUSES = {"draft", "confirmed"}


def _round(value: float) -> float:
    return round(float(value), 2)


def _gen_quotation_no() -> str:
    year = datetime.now(UTC).year
    return f"QT-{year}-{str(uuid4())[:6].upper()}"


async def _validate_quotation_items(
    item_ids: list[UUID], db: AsyncSession
) -> dict[UUID, Product]:
    """校验产品存在、未删除、status=active，并去重。"""
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


def _compute_totals(items: list[QuotationItem], discount: float) -> tuple[float, float]:
    """item subtotal = unit_price * qty（未税）。
    total = sum(subtotal * (1 + item.tax_rate)) * discount，2位。
    """
    subtotal_total = 0.0
    for it in items:
        it.subtotal = _round(it.unit_price * it.quantity)
        subtotal_total += it.subtotal
    subtotal_total = _round(subtotal_total)
    total_amount = _round(
        sum(it.subtotal * (1 + it.tax_rate) for it in items) * discount
    )
    return subtotal_total, total_amount


def _enrich_quotation_item(
    item: QuotationItem,
    product: Product | None,
    cover_url: str | None,
) -> dict:
    return {
        "id": str(item.id),
        "product_id": str(item.product_id),
        "product_no": product.product_no if product else None,
        "product_name": product.product_name if product else None,
        "face_price": product.face_price if product else None,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "tax_rate": item.tax_rate,
        "subtotal": item.subtotal,
        "cover_image_url": cover_url,
    }


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


def _quotation_to_dict(quotation: Quotation) -> dict:
    from datetime import datetime

    def _iso(v):
        return v.isoformat() if isinstance(v, datetime) else v

    return {
        "id": str(quotation.id),
        "quotation_no": quotation.quotation_no,
        "proposal_id": str(quotation.proposal_id),
        "creator_id": str(quotation.creator_id),
        "valid_until": _iso(quotation.valid_until),
        "total_amount": quotation.total_amount,
        "subtotal": quotation.subtotal,
        "tax_rate": quotation.tax_rate,
        "discount": quotation.discount,
        "status": quotation.status,
        "create_time": _iso(quotation.create_time),
        "update_time": _iso(quotation.update_time),
    }


async def _enrich_quotation_detail(
    quotation: Quotation, request: Request, db: AsyncSession
) -> dict:
    product_ids = [it.product_id for it in quotation.items]
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
    for it in quotation.items:
        prod = prod_map.get(it.product_id)
        enriched.append(_enrich_quotation_item(it, prod, cover_urls.get(it.product_id)))

    return {**_quotation_to_dict(quotation), "items": enriched}


async def _proposal_meta(proposal_id: UUID, db: AsyncSession) -> tuple[str, str]:
    """Return (proposal_no, proposal_name)."""
    prop = (
        await db.execute(
            select(Proposal).where(Proposal.id == proposal_id, Proposal.is_deleted.is_(False))
        )
    ).scalar_one_or_none()
    if not prop:
        return "", ""
    return prop.proposal_no, prop.proposal_name


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("quotation:view"))])
@audit_action("quotation_list", module="quotations")
async def list_quotations(
    request: Request,
    proposal_id: UUID | None = Query(None),
    q_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Quotation)
        .options(selectinload(Quotation.items))
        .where(Quotation.is_deleted.is_(False))
    )
    if proposal_id is not None:
        stmt = stmt.where(Quotation.proposal_id == proposal_id)
    if q_status is not None:
        if q_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "非法状态值"}
            )
        stmt = stmt.where(Quotation.status == q_status)

    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()

    stmt = stmt.order_by(Quotation.create_time.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    proposal_ids = [row.proposal_id for row in rows]
    proposal_result = await db.execute(
        select(Proposal).where(
            Proposal.id.in_(proposal_ids), Proposal.is_deleted.is_(False)
        )
    ) if proposal_ids else None
    proposal_map = {
        proposal.id: proposal for proposal in proposal_result.scalars().all()
    } if proposal_result else {}
    enriched = []
    for r in rows:
        proposal = proposal_map.get(r.proposal_id)
        resp = _quotation_to_dict(r)
        resp["proposal_no"] = proposal.proposal_no if proposal else ""
        resp["proposal_name"] = proposal.proposal_name if proposal else ""
        enriched.append(resp)

    return {
        "code": 200,
        "data": {
            "list": enriched,
            "total": total,
            "page": page,
            "size": size,
        },
    }


@router.get(
    "/{quotation_id}/pdf",
    dependencies=[Depends(PermissionChecker("quotation:view"))],
    responses={200: {"content": {"application/pdf": {}}}},
)
@audit_action("quotation_pdf_export", module="quotations", target_id_kwarg="quotation_id")
async def export_quotation_pdf(
    request: Request, quotation_id: UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Quotation)
        .options(selectinload(Quotation.items))
        .where(Quotation.id == quotation_id, Quotation.is_deleted.is_(False))
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "报价单不存在"})

    # 富化产品字段
    product_ids = [it.product_id for it in quotation.items]
    prod_map: dict[UUID, Product] = {}
    if product_ids:
        prod_result = await db.execute(
            select(Product).where(
                Product.id.in_(product_ids), Product.is_deleted.is_(False)
            )
        )
        prod_map = {p.id: p for p in prod_result.scalars().all()}

    gotenberg_url = settings.GOTENBERG_URL.rstrip("/")
    if not gotenberg_url:
        raise HTTPException(status_code=503, detail={"code": 50301, "msg": "PDF 服务未配置"})

    rows_html = "".join(
        f"""
        <tr>
          <td>{escape(str(prod_map.get(item.product_id) and prod_map[item.product_id].product_no or item.product_id))}</td>
          <td>{escape(str(prod_map.get(item.product_id) and prod_map[item.product_id].product_name or "-"))}</td>
          <td class="num">{item.quantity}</td>
          <td class="num">{_round(item.unit_price):.2f}</td>
          <td class="num">{_round(item.tax_rate * 100):.2f}%</td>
          <td class="num">{_round(item.subtotal):.2f}</td>
        </tr>
        """
        for item in quotation.items
    )
    valid_until = quotation.valid_until.strftime("%Y-%m-%d") if quotation.valid_until else "-"
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Quotation {escape(quotation.quotation_no)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #1f2937; margin: 32px; }}
    h1 {{ color: #0f172a; margin-bottom: 8px; }}
    .meta {{ margin: 16px 0 24px; line-height: 1.8; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; }}
    th {{ background: #f3f4f6; text-align: left; }}
    .num {{ text-align: right; }}
    .total {{ margin-top: 20px; text-align: right; line-height: 1.8; }}
  </style>
</head>
<body>
  <h1>报价单</h1>
  <div class="meta">
    <div>报价单号：{escape(quotation.quotation_no)}</div>
    <div>方案：{escape(quotation.proposal.proposal_name if quotation.proposal else "-")}</div>
    <div>状态：{escape(quotation.status or "-")}</div>
    <div>有效期：{escape(valid_until)}</div>
  </div>
  <table>
    <thead>
      <tr>
        <th>产品编号</th>
        <th>产品名称</th>
        <th class="num">数量</th>
        <th class="num">单价</th>
        <th class="num">税率</th>
        <th class="num">小计</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <div class="total">
    <div>折扣：{_round(quotation.discount * 100):.2f}%</div>
    <div>合计（含税后折前）：{_round(sum(it.subtotal * (1 + it.tax_rate) for it in quotation.items)):.2f}</div>
    <strong>总计：{_round(quotation.total_amount):.2f}</strong>
  </div>
</body>
</html>"""
    files = {"files": ("index.html", html.encode("utf-8"), "text/html")}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            pdf_resp = await client.post(
                f"{gotenberg_url}/forms/chromium/convert/html", files=files
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503, detail={"code": 50302, "msg": "PDF 服务不可用"}
        ) from exc

    if pdf_resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "code": 50201,
                "msg": "PDF 服务生成失败",
                "upstream_status": pdf_resp.status_code,
            },
        )

    return Response(
        content=pdf_resp.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{quotation.quotation_no}.pdf"'},
    )


@router.get(
    "/{quotation_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("quotation:view"))],
)
@audit_action("quotation_detail", module="quotations", target_id_kwarg="id")
async def get_quotation(request: Request, quotation_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Quotation)
        .options(selectinload(Quotation.items))
        .where(Quotation.id == quotation_id, Quotation.is_deleted.is_(False))
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "报价单不存在"})
    resp = await _enrich_quotation_detail(quotation, request, db)
    pno, pname = await _proposal_meta(quotation.proposal_id, db)
    resp["proposal_no"] = pno
    resp["proposal_name"] = pname
    return {"code": 200, "data": resp}


@router.post("", response_model=dict, status_code=201)
@audit_action("quotation_create", module="quotations", target_id_kwarg="id")
async def create_quotation(
    request: Request,
    quotation_data: QuotationCreate,
    current_user: dict = Depends(PermissionChecker("quotation:create")),
    db: AsyncSession = Depends(get_db),
):
    proposal_result = await db.execute(
        select(Proposal).where(
            Proposal.id == quotation_data.proposal_id, Proposal.is_deleted.is_(False)
        )
    )
    proposal = proposal_result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "关联方案不存在"})

    products = await _validate_quotation_items(
        [i.product_id for i in quotation_data.items], db
    )

    quotation = Quotation(
        quotation_no=_gen_quotation_no(),
        proposal_id=quotation_data.proposal_id,
        creator_id=UUID(current_user["sub"]),
        tax_rate=quotation_data.tax_rate,
        discount=quotation_data.discount,
        valid_until=quotation_data.valid_until,
        status="draft",
    )
    db.add(quotation)
    await db.flush()

    items = []
    for item_data in quotation_data.items:
        item = QuotationItem(
            quotation_id=quotation.id,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            tax_rate=item_data.tax_rate,
            subtotal=0.0,
        )
        items.append(item)
        db.add(item)

    subtotal_total, total_amount = _compute_totals(items, quotation.discount)
    quotation.subtotal = subtotal_total
    quotation.total_amount = total_amount

    await db.commit()
    await db.refresh(quotation)
    await db.refresh(quotation, ["items"])
    resp = await _enrich_quotation_detail(quotation, request, db)
    pno, pname = await _proposal_meta(quotation.proposal_id, db)
    resp["proposal_no"] = pno
    resp["proposal_name"] = pname
    return {"code": 200, "data": resp}


@router.put(
    "/{quotation_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("quotation:edit"))],
)
@audit_action("quotation_update", module="quotations", target_id_kwarg="id")
async def update_quotation(
    request: Request,
    quotation_id: UUID,
    quotation_data: QuotationUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Quotation)
        .options(selectinload(Quotation.items))
        .where(Quotation.id == quotation_id, Quotation.is_deleted.is_(False))
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "报价单不存在"})

    if quotation.status == "confirmed":
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "报价单已确认，不可修改"}
        )

    # 只更新 model_fields_set 中的可选字段
    if "tax_rate" in quotation_data.model_fields_set:
        quotation.tax_rate = quotation_data.tax_rate
    if "discount" in quotation_data.model_fields_set:
        quotation.discount = quotation_data.discount
    if "valid_until" in quotation_data.model_fields_set:
        quotation.valid_until = quotation_data.valid_until
    if "status" in quotation_data.model_fields_set:
        quotation.status = quotation_data.status

    items = quotation.items
    if "items" in quotation_data.model_fields_set:
        new_items = quotation_data.items
        if new_items is not None and not new_items:
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "报价明细不可为空"}
            )
        if new_items is not None:
            products = await _validate_quotation_items(
                [i.product_id for i in new_items], db
            )
            old_items = await db.execute(
                select(QuotationItem).where(QuotationItem.quotation_id == quotation.id)
            )
            for old in old_items.scalars().all():
                await db.delete(old)
            items = []
            for item_data in new_items:
                item = QuotationItem(
                    quotation_id=quotation.id,
                    product_id=item_data.product_id,
                    quantity=item_data.quantity,
                    unit_price=item_data.unit_price,
                    tax_rate=item_data.tax_rate,
                    subtotal=0.0,
                )
                items.append(item)
                db.add(item)

    subtotal_total, total_amount = _compute_totals(items, quotation.discount)
    quotation.subtotal = subtotal_total
    quotation.total_amount = total_amount

    await db.commit()
    await db.refresh(quotation)
    await db.refresh(quotation, ["items"])
    resp = await _enrich_quotation_detail(quotation, request, db)
    pno, pname = await _proposal_meta(quotation.proposal_id, db)
    resp["proposal_no"] = pno
    resp["proposal_name"] = pname
    return {"code": 200, "data": resp}


@router.post(
    "/{quotation_id}/confirm",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("quotation:confirm"))],
)
async def confirm_quotation(
    request: Request,
    quotation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """V1.2 §5.6 — idempotent quotation confirmation.

    Repeating the confirm call with the same quotation id MUST NOT create
    additional OperationLog rows or downstream state changes. We do this by
    short-circuiting early (before the ``@audit_action`` decorator path is
    needed) when the quotation is already confirmed — and by writing the
    audit row only on the actual transition.
    """
    result = await db.execute(
        select(Quotation)
        .options(selectinload(Quotation.items))
        .where(Quotation.id == quotation_id, Quotation.is_deleted.is_(False))
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "报价单不存在"})
    if quotation.status == "confirmed":
        resp = await _enrich_quotation_detail(quotation, request, db)
        pno, pname = await _proposal_meta(quotation.proposal_id, db)
        resp["proposal_no"] = pno
        resp["proposal_name"] = pname
        return {"code": 200, "data": resp}
    if not quotation.items:
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "报价明细为空，不可确认"}
        )

    quotation.status = "confirmed"

    from app.middleware.audit import _client_ip, _user_id_from_request, _write_operation_log

    ip = _client_ip(request)
    user_id = _user_id_from_request(request)
    await _write_operation_log(
        user_id=user_id,
        module="quotations",
        action="quotation_confirm",
        target_id=str(quotation.id),
        response_code=200,
        ip=ip,
    )

    await db.commit()
    await db.refresh(quotation)
    await db.refresh(quotation, ["items"])
    resp = await _enrich_quotation_detail(quotation, request, db)
    pno, pname = await _proposal_meta(quotation.proposal_id, db)
    resp["proposal_no"] = pno
    resp["proposal_name"] = pname
    return {"code": 200, "data": resp}
