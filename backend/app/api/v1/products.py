import io
from decimal import Decimal
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.serializers import filter_sensitive_fields
from app.middleware.audit import audit_action
from app.models.product import Brand, Category, Product, ProductTag, Supplier, Tag
from app.schemas.product import (
    ProductCloneResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.services.products_export import (
    build_excel_bytes,
    count_products_for_export,
    fetch_products_for_export,
)

router = APIRouter()


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("product:view"))])
async def list_products(
    request: Request,
    category_id: UUID | None = None,
    tag_ids: str | None = None,
    keyword: str | None = None,
    brand_id: UUID | None = None,
    supplier_id: UUID | None = None,
    status: str | None = None,
    stock_status: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).options(selectinload(Product.tags)).where(Product.is_deleted.is_(False))

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
        query = query.where(Product.face_price >= min_price)
    if max_price is not None:
        query = query.where(Product.face_price <= max_price)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    products = result.scalars().all()
    items = [ProductResponse.model_validate(p).model_dump(mode="json") for p in products]
    role_code = getattr(request.state, "role_code", None) or "sales"
    items = filter_sensitive_fields(items, role_code)
    return {
        "code": 200,
        "data": {
            "list": items,
            "total": total,
            "page": page,
            "size": size,
        },
    }


# 注意：静态路径 /export 必须在动态路径 /{product_id} 之前注册，否则会被
# /{product_id} 抢占匹配（"export" 会被当作 product_id）。
@router.get("/export", dependencies=[Depends(PermissionChecker("product:export"))])
async def export_products(
    request: Request,
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
    role_code = getattr(request.state, "role_code", None) or "sales"

    rows = await fetch_products_for_export(
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

    total = await count_products_for_export(
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

    excel_bytes = build_excel_bytes(rows, role_code=role_code)

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="products_export.xlsx"',
            "X-Total-Count": str(total),
        },
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    dependencies=[Depends(PermissionChecker("product:view"))],
)
async def get_product(
    request: Request,
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.tags))
        .where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})
    body = ProductResponse.model_validate(product).model_dump(mode="json")
    role_code = getattr(request.state, "role_code", None)
    return filter_sensitive_fields(body, role_code or "sales")


@router.post(
    "",
    response_model=ProductResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker("product:create"))],
)
@audit_action("product_create", module="products", target_id_kwarg="id")
async def create_product(
    request: Request, product_data: ProductCreate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Product).options(selectinload(Product.tags)).where(
            Product.product_no == product_data.product_no, Product.is_deleted.is_(False)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail={"code": 40901, "msg": "产品编号已存在"})

    product = Product(**product_data.model_dump(exclude={"tag_ids"}))
    db.add(product)
    await db.flush()

    if product_data.tag_ids:
        for tag_id in product_data.tag_ids:
            db.add(ProductTag(product_id=product.id, tag_id=tag_id))

    await db.commit()
    await db.refresh(product)
    await db.refresh(product, ["tags"])
    return product


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    dependencies=[Depends(PermissionChecker("product:edit"))],
)
async def update_product(
    product_id: UUID, product_data: ProductUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.tags))
        .where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})

    for field, value in product_data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", dependencies=[Depends(PermissionChecker("product:delete"))])
@audit_action("product_delete", module="products")
async def delete_product(request: Request, product_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.tags))
        .where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})

    product.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}


@router.patch(
    "/{product_id}/status",
    dependencies=[Depends(PermissionChecker("product:status"))],
)
@audit_action("product_status", module="products")
async def update_product_status(
    request: Request, product_id: UUID, status_data: dict, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.tags))
        .where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})

    product.status = status_data.get("status", "draft")
    await db.commit()
    await db.refresh(product)
    return {"code": 200, "msg": "success"}


@router.post(
    "/{product_id}/clone",
    response_model=ProductCloneResponse,
    dependencies=[Depends(PermissionChecker("product:clone"))],
)
@audit_action("product_clone", module="products")
async def clone_product(
    request: Request,
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.tags))
        .where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})

    cloned = Product(
        product_no=f"{product.product_no}-COPY",
        product_name=f"{product.product_name} (副本)",
        brand_id=product.brand_id,
        supplier_id=product.supplier_id,
        category_id=product.category_id,
        face_price=product.face_price,
        cost_price=product.cost_price,
        material=product.material,
        status="draft",
    )
    db.add(cloned)
    await db.flush()

    # 复制标签关联（除编号/附件/向量外，标签一并复制；不触发向量检索/Embedding）
    tag_result = await db.execute(select(ProductTag).where(ProductTag.product_id == product.id))
    for pt in tag_result.scalars().all():
        db.add(ProductTag(product_id=cloned.id, tag_id=pt.tag_id))

    await db.commit()
    await db.refresh(cloned)
    body = ProductCloneResponse.model_validate(cloned).model_dump(mode="json")
    role_code = getattr(request.state, "role_code", None)
    return filter_sensitive_fields(body, role_code or "sales")


@router.post("/import", dependencies=[Depends(PermissionChecker("product:import"))])
@audit_action("product_import", module="products")
async def import_products(
    request: Request,
    file: UploadFile = File(...),
    skip_if_exists: bool = Query(False, alias="skipIfExists"),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail={"code": 40001, "msg": f"文件解析失败: {e}"}
        ) from e

    required_cols = {"product_no", "product_name", "face_price"}
    if not required_cols.issubset(set(df.columns)):
        missing = required_cols - set(df.columns)
        raise HTTPException(
            status_code=400, detail={"code": 40002, "msg": f"缺少必填列: {missing}"}
        )

    brand_names = df.get("brand_name", pd.Series()).dropna().unique().tolist()
    supplier_names = df.get("supplier_name", pd.Series()).dropna().unique().tolist()
    category_names = df.get("category_name", pd.Series()).dropna().unique().tolist()
    tag_names = set()
    if "tag_names" in df.columns:
        for v in df["tag_names"].dropna():
            tag_names.update([t.strip() for t in str(v).split(",") if t.strip()])

    brand_map = {}
    if brand_names:
        result = await db.execute(select(Brand).where(Brand.brand_name.in_(brand_names)))
        brand_map = {b.brand_name: b.id for b in result.scalars().all()}

    supplier_map = {}
    if supplier_names:
        result = await db.execute(
            select(Supplier).where(Supplier.supplier_name.in_(supplier_names))
        )
        supplier_map = {s.supplier_name: s.id for s in result.scalars().all()}

    category_map = {}
    if category_names:
        result = await db.execute(
            select(Category).where(Category.category_name.in_(category_names))
        )
        category_map = {c.category_name: c.id for c in result.scalars().all()}

    tag_map = {}
    if tag_names:
        result = await db.execute(select(Tag).where(Tag.tag_name.in_(tag_names)))
        tag_map = {t.tag_name: t.id for t in result.scalars().all()}

    success_count = 0
    failures = []
    total = len(df)

    for idx, row in df.iterrows():
        row_num = idx + 2
        product_no = str(row.get("product_no", "")).strip()
        product_name = str(row.get("product_name", "")).strip()

        if not product_no or not product_name:
            failures.append(
                {
                    "row": row_num,
                    "product_no": product_no,
                    "reason": "product_no 或 product_name 为空",
                }
            )
            continue

        existing = await db.execute(
            select(Product)
        .options(selectinload(Product.tags))
        .where(Product.product_no == product_no, Product.is_deleted.is_(False))
        )
        if existing.scalar_one_or_none():
            if skip_if_exists:
                failures.append(
                    {"row": row_num, "product_no": product_no, "reason": "编号已存在，已跳过"}
                )
                continue
            else:
                failures.append(
                    {"row": row_num, "product_no": product_no, "reason": "产品编号已存在"}
                )
                continue

        brand_name = (
            str(row.get("brand_name", "")).strip() if pd.notna(row.get("brand_name")) else None
        )
        supplier_name = (
            str(row.get("supplier_name", "")).strip()
            if pd.notna(row.get("supplier_name"))
            else None
        )
        category_name = (
            str(row.get("category_name", "")).strip()
            if pd.notna(row.get("category_name"))
            else None
        )

        brand_id = brand_map.get(brand_name) if brand_name else None
        supplier_id = supplier_map.get(supplier_name) if supplier_name else None
        category_id = category_map.get(category_name) if category_name else None

        if not brand_id or not supplier_id or not category_id:
            missing = []
            if brand_name and not brand_id:
                missing.append(f"品牌'{brand_name}'不存在")
            if supplier_name and not supplier_id:
                missing.append(f"供应商'{supplier_name}'不存在")
            if category_name and not category_id:
                missing.append(f"分类'{category_name}'不存在")
            failures.append(
                {"row": row_num, "product_no": product_no, "reason": "; ".join(missing)}
            )
            continue

        face_price = float(row.get("face_price", 0))
        cost_price = float(row["cost_price"]) if pd.notna(row.get("cost_price")) else None
        material = str(row["material"]).strip() if pd.notna(row.get("material")) else None
        stock_status = str(row.get("stock_status", "in_stock")).strip()
        status = str(row.get("status", "draft")).strip()

        product = Product(
            product_no=product_no,
            product_name=product_name,
            brand_id=brand_id,
            supplier_id=supplier_id,
            category_id=category_id,
            face_price=face_price,
            cost_price=cost_price,
            material=material,
            stock_status=stock_status,
            status=status,
        )
        db.add(product)
        await db.flush()

        if "tag_names" in df.columns and pd.notna(row.get("tag_names")):
            tag_list = [t.strip() for t in str(row["tag_names"]).split(",") if t.strip()]
            for tag_name in tag_list:
                tag_id = tag_map.get(tag_name)
                if tag_id:
                    db.add(ProductTag(product_id=product.id, tag_id=tag_id))

        success_count += 1

    await db.commit()

    return {
        "code": 200,
        "data": {
            "total": total,
            "success_count": success_count,
            "fail_count": len(failures),
            "failures": failures,
        },
    }
