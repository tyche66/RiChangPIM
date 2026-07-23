"""产品导出服务模块。

独立 service，可被复用（如导出、导入对比、报表生成等）。
依赖：pandas + openpyxl（已在 requirements-dev.txt 声明）。
"""

from __future__ import annotations

import io
from uuid import UUID

import pandas as pd
from sqlalchemy import func, select

import app.models.doc_chunk  # noqa: F401 - register Product relationship target
from app.core.database import AsyncSessionLocal
from app.models.product import Brand, Category, Product, ProductTag, Supplier, Tag

FIELD_MAP = {
    "product_id": "id",
    "product_no": "product_no",
    "product_name": "product_name",
    "brand_name": "brand_name",
    "supplier_name": "supplier_name",
    "category_name": "category_name",
    "face_price": "face_price",
    "cost_price": "cost_price",
    "material": "material",
    "stock_status": "stock_status",
    "status": "status",
    "description": "description",
    "specification": "specification",
    "colors": "colors",
    "data_source": "data_source",
    "completeness_status": "completeness_status",
    "create_time": "create_time",
    "update_time": "update_time",
}

# 导出 Excel 列头中文映射（键与 FIELD_MAP 保持一致）。
HEADER_MAP = {
    "product_id": "产品ID",
    "product_no": "产品编号",
    "product_name": "产品名称",
    "brand_name": "品牌",
    "supplier_name": "供应商",
    "category_name": "分类",
    "face_price": "面价",
    "cost_price": "成本价",
    "material": "材质",
    "stock_status": "库存状态",
    "status": "状态",
    "description": "描述",
    "specification": "规格",
    "colors": "颜色",
    "data_source": "数据来源",
    "completeness_status": "完整度状态",
    "create_time": "创建时间",
    "update_time": "更新时间",
    "tags": "标签",
}


def _build_query(
    *,
    category_id: UUID | None = None,
    tag_ids: str | None = None,
    keyword: str | None = None,
    brand_id: UUID | None = None,
    supplier_id: UUID | None = None,
    status: str | None = None,
    stock_status: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
):
    """构建与 GET /products 一致的过滤查询。"""
    query = select(Product).where(Product.is_deleted.is_(False))

    if category_id:
        query = query.where(Product.category_id == category_id)
    if brand_id:
        query = query.where(Product.brand_id == brand_id)
    if supplier_id:
        query = query.where(Product.supplier_id == supplier_id)
    if status:
        query = query.where(Product.status == status)
    if stock_status:
        query = query.where(Product.stock_status == stock_status)
    if keyword:
        query = query.where(
            (Product.product_name.ilike(f"%{keyword}%"))
            | (Product.product_no.ilike(f"%{keyword}%"))
        )
    if min_price is not None:
        query = query.where(Product.face_price != 99999, Product.face_price >= min_price)
    if max_price is not None:
        query = query.where(Product.face_price != 99999, Product.face_price <= max_price)

    if tag_ids:
        tag_id_list = [UUID(t.strip()) for t in tag_ids.split(",") if t.strip()]
        if tag_id_list:
            subq = select(ProductTag.product_id).where(
                ProductTag.tag_id.in_(tag_id_list), ProductTag.is_deleted.is_(False)
            )
            query = query.where(Product.id.in_(subq))

    return query


async def fetch_products_for_export(
    *,
    category_id: UUID | None = None,
    tag_ids: str | None = None,
    keyword: str | None = None,
    brand_id: UUID | None = None,
    supplier_id: UUID | None = None,
    status: str | None = None,
    stock_status: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """执行查询并返回扁平化的产品记录列表（含关联名）。"""
    query = _build_query(
        category_id=category_id,
        tag_ids=tag_ids,
        keyword=keyword,
        brand_id=brand_id,
        supplier_id=supplier_id,
        status=status,
        stock_status=stock_status,
        min_price=min_price,
        max_price=max_price,
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(query)
        products = result.scalars().all()

        if not products:
            return []

        product_ids = [p.id for p in products]
        brand_map = {}
        supplier_map = {}
        category_map = {}
        tag_map = {}

        if product_ids:
            brand_result = await session.execute(
                select(Brand).where(Brand.id.in_({p.brand_id for p in products}))
            )
            brand_map = {b.id: b.brand_name for b in brand_result.scalars().all()}

            supplier_result = await session.execute(
                select(Supplier).where(Supplier.id.in_({p.supplier_id for p in products}))
            )
            supplier_map = {s.id: s.supplier_name for s in supplier_result.scalars().all()}

            category_result = await session.execute(
                select(Category).where(Category.id.in_({p.category_id for p in products}))
            )
            category_map = {c.id: c.category_name for c in category_result.scalars().all()}

            tag_result = await session.execute(
                select(ProductTag, Tag)
                .join(Tag, ProductTag.tag_id == Tag.id)
                .where(
                    ProductTag.product_id.in_(product_ids),
                    ProductTag.is_deleted.is_(False),
                    Tag.is_deleted.is_(False),
                )
            )
            for pt, tag in tag_result.all():
                tag_map.setdefault(pt.product_id, []).append(tag.tag_name)

    rows = []
    for p in products:
        row = {
            "product_id": str(p.id),
            "product_no": p.product_no,
            "product_name": p.product_name,
            "brand_name": brand_map.get(p.brand_id),
            "supplier_name": supplier_map.get(p.supplier_id),
            "category_name": category_map.get(p.category_id),
            "face_price": "待核价" if p.face_price == 99999 else p.face_price,
            "cost_price": p.cost_price,
            "material": p.material,
            "stock_status": p.stock_status,
            "status": p.status,
            "description": p.description,
            "specification": p.specification,
            "colors": p.colors,
            "data_source": p.data_source,
            "completeness_status": p.completeness_status,
            "create_time": p.create_time.isoformat() if p.create_time else "",
            "update_time": p.update_time.isoformat() if p.update_time else "",
            "tags": ", ".join(tag_map.get(p.id, [])),
        }
        rows.append(row)

    return rows


def build_excel_bytes(rows: list[dict], role_code: str = "admin") -> bytes:
    """将 rows 转为 Excel 二进制流。

    role_code != 'sales' 时保留 cost_price；sales 角色该列置零。
    """
    df = pd.DataFrame(rows, columns=list(FIELD_MAP.keys()) + ["tags"])

    fields = list(FIELD_MAP.keys())
    if role_code in {"sales", "viewer"}:
        fields = [field for field in fields if field not in {"cost_price", "supplier_name"}]

    df = df[fields + ["tags"]]

    df = df.rename(columns=HEADER_MAP)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Products")
    return output.getvalue()


async def count_products_for_export(
    *,
    category_id: UUID | None = None,
    tag_ids: str | None = None,
    keyword: str | None = None,
    brand_id: UUID | None = None,
    supplier_id: UUID | None = None,
    status: str | None = None,
    stock_status: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> int:
    """返回符合条件的产品总数（用于导出前预估 / 响应头计数）。"""
    query = _build_query(
        category_id=category_id,
        tag_ids=tag_ids,
        keyword=keyword,
        brand_id=brand_id,
        supplier_id=supplier_id,
        status=status,
        stock_status=stock_status,
        min_price=min_price,
        max_price=max_price,
    )
    query = select(func.count()).select_from(query.subquery())

    async with AsyncSessionLocal() as session:
        result = await session.execute(query)
        return result.scalar() or 0
