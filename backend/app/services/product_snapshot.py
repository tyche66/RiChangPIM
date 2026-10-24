"""产品事实快照（Track C）。

服务端在创建/修改方案或报价明细时，从产品表读取事实并生成快照，
**不信任前端传入的产品事实**。

读取优先级（历史方案稳定展示的关键）：

1. ``product_snapshot``（历史快照，产品改名/改材质也不会漂移）；
2. 当前产品字段；
3. 空值 -> 「资料未提供」。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product

MISSING_TEXT = "资料未提供"


async def build_product_snapshot(db: AsyncSession, product_id: UUID) -> dict[str, Any] | None:
    """从产品表读取事实并生成快照。产品不存在或已删除时返回 None。

    ``category`` 关系必须 eager load：异步 session 里访问延迟加载的关系会抛
    ``MissingGreenlet``（曾导致创建方案/报价明细时 500）。
    """
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.category))
        .where(
            Product.id == product_id,
            Product.is_deleted.is_(False),
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        return None
    return {
        "product_no": product.product_no,
        "product_name": product.product_name,
        "category_name": (
            product.category.category_name if product.category else None
        ),
        "material": product.material,
        "colors": product.colors,
        "material_description": product.material_description,
        "specification": product.specification,
        "face_price": (
            None if product.face_price == 99999 else product.face_price
        ),
    }


def merge_snapshot(
    snapshot: dict[str, Any] | None, product: Product | None
) -> dict[str, Any]:
    """按优先级合并展示字段：快照优先，其次当前产品，最后缺失文案。"""
    snapshot = snapshot or {}
    current = {
        "product_no": getattr(product, "product_no", None),
        "product_name": getattr(product, "product_name", None),
        "category_name": (
            product.category.category_name if product and product.category else None
        ),
        "material": getattr(product, "material", None),
        "colors": getattr(product, "colors", None),
        "material_description": getattr(product, "material_description", None),
        "specification": getattr(product, "specification", None),
        "face_price": (
            None
            if product is None or getattr(product, "face_price", None) in (None, 99999)
            else product.face_price
        ),
    }
    out: dict[str, Any] = {}
    for key, value in current.items():
        chosen = snapshot.get(key)
        if chosen in (None, "", []):
            chosen = value
        out[key] = chosen if chosen not in (None, "", []) else MISSING_TEXT
    return out


def display_value(value: Any) -> str:
    """单个字段的展示值：空 -> 资料未提供。"""
    if value in (None, "", []):
        return MISSING_TEXT
    return str(value)
