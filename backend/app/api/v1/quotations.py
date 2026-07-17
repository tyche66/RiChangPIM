from datetime import UTC, datetime
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
from app.middleware.audit import audit_action
from app.models.sales import Proposal, Quotation, QuotationItem
from app.schemas.quotation import (
    QuotationCreate,
    QuotationResponse,
    QuotationUpdate,
)

router = APIRouter()


def _round(value: float) -> float:
    return round(float(value), 2)


def _gen_quotation_no() -> str:
    year = datetime.now(UTC).year
    return f"QT-{year}-{str(uuid4())[:6].upper()}"


def _compute_totals(items, tax_rate: float, discount: float):
    """后端计算每项小计及折扣、税率调整后的总价。"""
    subtotal_total = 0.0
    for it in items:
        it.subtotal = _round(it.unit_price * it.quantity)
        subtotal_total += it.subtotal
    subtotal_total = _round(subtotal_total)
    total_amount = _round(subtotal_total * discount * (1 + tax_rate))
    return subtotal_total, total_amount


def _render_quotation_html(quotation: Quotation) -> str:
    rows = "".join(
        f"""
        <tr>
          <td>{escape(str(item.product_id))}</td>
          <td class="num">{item.quantity}</td>
          <td class="num">{_round(item.unit_price):.2f}</td>
          <td class="num">{_round(item.tax_rate * 100):.2f}%</td>
          <td class="num">{_round(item.subtotal):.2f}</td>
        </tr>
        """
        for item in quotation.items
    )
    valid_until = quotation.valid_until.strftime("%Y-%m-%d") if quotation.valid_until else "-"
    return f"""<!doctype html>
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
    <div>状态：{escape(quotation.status or "-")}</div>
    <div>有效期：{escape(valid_until)}</div>
  </div>
  <table>
    <thead>
      <tr>
        <th>产品 ID</th>
        <th class="num">数量</th>
        <th class="num">单价</th>
        <th class="num">税率</th>
        <th class="num">小计</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <div class="total">
    <div>折扣：{_round(quotation.discount * 100):.2f}%</div>
    <div>整单税率：{_round(quotation.tax_rate * 100):.2f}%</div>
    <strong>总计：{_round(quotation.total_amount):.2f}</strong>
  </div>
</body>
</html>"""


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
        stmt = stmt.where(Quotation.status == q_status)

    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()

    stmt = stmt.order_by(Quotation.create_time.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "code": 200,
        "data": {
            "list": [QuotationResponse.model_validate(r) for r in rows],
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

    gotenberg_url = settings.GOTENBERG_URL.rstrip("/")
    if not gotenberg_url:
        raise HTTPException(status_code=503, detail={"code": 50301, "msg": "PDF 服务未配置"})

    html = _render_quotation_html(quotation)
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
    response_model=QuotationResponse,
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
    return quotation


@router.post("", response_model=QuotationResponse, status_code=201)
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

    subtotal_total, total_amount = _compute_totals(items, quotation.tax_rate, quotation.discount)
    quotation.subtotal = subtotal_total
    quotation.total_amount = total_amount

    await db.commit()
    await db.refresh(quotation)
    await db.refresh(quotation, ["items"])
    return quotation


@router.put(
    "/{quotation_id}",
    response_model=QuotationResponse,
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

    if quotation_data.tax_rate is not None:
        quotation.tax_rate = quotation_data.tax_rate
    if quotation_data.discount is not None:
        quotation.discount = quotation_data.discount
    if quotation_data.valid_until is not None:
        quotation.valid_until = quotation_data.valid_until
    if quotation_data.status is not None:
        quotation.status = quotation_data.status

    if quotation_data.items is not None:
        existing = await db.execute(
            select(QuotationItem).where(QuotationItem.quotation_id == quotation.id)
        )
        for old in existing.scalars().all():
            await db.delete(old)
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
        subtotal_total, total_amount = _compute_totals(
            items, quotation.tax_rate, quotation.discount
        )
        quotation.subtotal = subtotal_total
        quotation.total_amount = total_amount

    await db.commit()
    await db.refresh(quotation)
    await db.refresh(quotation, ["items"])
    return quotation


@router.post(
    "/{quotation_id}/confirm",
    response_model=QuotationResponse,
    dependencies=[Depends(PermissionChecker("quotation:confirm"))],
)
@audit_action("quotation_confirm", module="quotations", target_id_kwarg="quotation_id")
async def confirm_quotation(
    request: Request,
    quotation_id: UUID,
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
        return quotation

    quotation.status = "confirmed"
    await db.commit()
    await db.refresh(quotation)
    await db.refresh(quotation, ["items"])
    return quotation
