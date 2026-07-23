"""V1.2 pilot data quality service.

Computes lightweight completeness flags from existing product relationships
(ProductImage, ProductManual, supplier, category) WITHOUT introducing new
table columns — the V1.2 brief allows derived flags, and this minimizes the
migration risk surface for the V1.2 RC window.

Quality flags returned per product (all boolean, derived):
- ``no_price``           face_price == 99999 (placeholder) OR NULL
- ``no_image``           no rows in product_image
- ``no_manual``          no rows in product_manual
- ``no_spec``            specification IS NULL OR empty
- ``source_incomplete``  data_source IS NULL OR empty
- ``ocr_failed``         any product_manual with parse_status = 'failed'
- ``long_pending``       completeness_status = 'pending' AND age > N days

These flags are conservative — they only ever surface as filters/exports and
NEVER mutate product data. AI-suggested guesses are forbidden by the V1.2
business red line (docs/v1.2-plan.md §5.4).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import (
    Product,
    ProductImage,
    ProductManual,
    ProductTag,
    Supplier,
)

LONG_PENDING_DAYS = 14
_PLACEHOLDER_PRICE = 99999
PLACEHOLDER_PRICE_LABEL = "待核价"

_VALID_QUALITY_FLAGS = frozenset({
    None,
    "no_price",
    "no_image",
    "no_manual",
    "no_spec",
    "source_incomplete",
    "ocr_failed",
    "long_pending",
})


def is_valid_quality_flag(flag: str | None) -> bool:
    return flag in _VALID_QUALITY_FLAGS


def _apply_quality_filter(
    stmt,
    *,
    completeness_status: str | None = None,
    quality_flag: str | None = None,
) -> Any:
    if completeness_status:
        stmt = stmt.where(Product.completeness_status == completeness_status)
    if quality_flag == "no_price":
        stmt = stmt.where(Product.face_price == _PLACEHOLDER_PRICE)
    elif quality_flag == "no_image":
        stmt = stmt.where(
            ~exists().where(ProductImage.product_id == Product.id)
        )
    elif quality_flag == "no_manual":
        stmt = stmt.where(
            ~exists().where(ProductManual.product_id == Product.id)
        )
    elif quality_flag == "no_spec":
        stmt = stmt.where(
            (Product.specification.is_(None)) | (func.btrim(Product.specification) == "")
        )
    elif quality_flag == "source_incomplete":
        stmt = stmt.where(
            (Product.data_source.is_(None)) | (func.btrim(Product.data_source) == "")
        )
    elif quality_flag == "ocr_failed":
        stmt = stmt.where(
            exists().where(
                ProductManual.product_id == Product.id,
                ProductManual.parse_status == "failed",
            )
        )
    elif quality_flag == "long_pending":
        cutoff = datetime.now() - timedelta(days=LONG_PENDING_DAYS)
        stmt = stmt.where(
            Product.completeness_status == "pending",
            Product.create_time <= cutoff,
        )
    return stmt


async def quality_summary(db: AsyncSession) -> dict[str, Any]:
    """Return aggregate counts per quality flag (for the Quality dashboard)."""
    counts: dict[str, Any] = {}
    base = select(Product).where(Product.is_deleted.is_(False))
    counts["total"] = await _count(db, base)

    for flag in (
        "no_price",
        "no_image",
        "no_manual",
        "no_spec",
        "source_incomplete",
        "ocr_failed",
        "long_pending",
    ):
        filtered = _apply_quality_filter(
            select(func.count()).select_from(Product).where(
                Product.is_deleted.is_(False)
            ),
            quality_flag=flag,
        )
        result = await db.execute(filtered)
        counts[flag] = int(result.scalar_one())

    comp_counts_stmt = (
        select(Product.completeness_status, func.count())
        .where(Product.is_deleted.is_(False))
        .group_by(Product.completeness_status)
    )
    rows = (await db.execute(comp_counts_stmt)).all()
    counts["by_completeness"] = {k or "unknown": int(v) for k, v in rows}
    return counts


async def _count(db: AsyncSession, stmt) -> int:
    wrapped = select(func.count()).select_from(stmt.subquery())
    result = await db.execute(wrapped)
    return int(result.scalar_one())


async def quality_rows(
    db: AsyncSession,
    *,
    completeness_status: str | None = None,
    quality_flag: str | None = None,
    supplier_id: UUID | None = None,
    category_id: UUID | None = None,
    series_tag_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Return products matching the quality view (without cost/sensitive supplier cols)."""
    base = (
        select(Product, Supplier.supplier_name)
        .outerjoin(Supplier, Supplier.id == Product.supplier_id)
        .where(Product.is_deleted.is_(False))
    )
    base = _apply_quality_filter(
        base,
        completeness_status=completeness_status,
        quality_flag=quality_flag,
    )
    if supplier_id:
        base = base.where(Product.supplier_id == supplier_id)
    if category_id:
        base = base.where(Product.category_id == category_id)
    if series_tag_id:
        base = base.join(
            ProductTag,
            and_(ProductTag.product_id == Product.id, ProductTag.is_deleted.is_(False)),
        ).where(ProductTag.tag_id == series_tag_id)
    base = base.order_by(Product.create_time.asc()).offset(offset).limit(limit)
    rows = (await db.execute(base)).all()

    out: list[dict] = []
    for product, supplier_name in rows:
        out.append({
            "id": str(product.id),
            "product_no": product.product_no,
            "product_name": product.product_name,
            "completeness_status": product.completeness_status,
            "face_price": product.face_price,
            "face_price_label": (
                PLACEHOLDER_PRICE_LABEL
                if product.face_price == _PLACEHOLDER_PRICE
                else str(product.face_price)
            ),
            "specification": product.specification,
            "data_source": product.data_source,
            "supplier_id": str(product.supplier_id),
            "supplier_name": supplier_name,
            "category_id": str(product.category_id),
            "brand_id": str(product.brand_id),
            "create_time": product.create_time.isoformat() if product.create_time else None,
            "update_time": product.update_time.isoformat() if product.update_time else None,
        })
    return out
