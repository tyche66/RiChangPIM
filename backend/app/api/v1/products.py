import datetime
import io
import logging
from decimal import Decimal
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.security import create_access_token
from app.core.serializers import filter_sensitive_fields
from app.middleware.audit import audit_action
from app.models.product import (
    Attachment,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductTag,
    SceneImage,
    Supplier,
    Tag,
    product_scene_image,
)
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

logger = logging.getLogger(__name__)

_PREVIEW_EXPIRE_SECONDS = 900
_CONTENT_TOKEN_SCOPE = "file_content"


def _create_content_url(request: Request, attachment_id: UUID) -> str:
    token = create_access_token(
        {
            "sub": getattr(request.state, "user_id", None) or "file-content",
            "scope": _CONTENT_TOKEN_SCOPE,
            "attachment_id": str(attachment_id),
        },
        expires_delta=datetime.timedelta(seconds=_PREVIEW_EXPIRE_SECONDS),
    )
    return f"/api/v1/files/{attachment_id}/content?token={token}"


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
    completeness_status: str | None = None,
    quality_flag: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    from app.services.quality import _apply_quality_filter, is_valid_quality_flag

    if not is_valid_quality_flag(quality_flag):
        raise HTTPException(
            status_code=422,
            detail={"code": 42206, "msg": f"quality_flag 不支持: {quality_flag}"},
        )

    query = select(Product).options(
        selectinload(Product.tags),
        joinedload(Product.brand),
        joinedload(Product.supplier),
        joinedload(Product.category),
        selectinload(Product.images).joinedload(ProductImage.attachment),
    ).where(Product.is_deleted.is_(False))

    if category_id:
        query = query.where(Product.category_id == category_id)
    if brand_id:
        query = query.where(Product.brand_id == brand_id)
    if supplier_id:
        query = query.where(Product.supplier_id == supplier_id)
    if tag_ids:
        try:
            parsed_tag_ids = [UUID(value.strip()) for value in tag_ids.split(",") if value.strip()]
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "tag_ids 格式无效"}
            ) from exc
        if parsed_tag_ids:
            query = (
                query.join(ProductTag)
                .where(
                    ProductTag.tag_id.in_(parsed_tag_ids),
                    ProductTag.is_deleted.is_(False),
                )
                .distinct()
            )
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

    query = _apply_quality_filter(
        query,
        completeness_status=completeness_status,
        quality_flag=quality_flag,
    )

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    products = result.scalars().all()
    items = [_product_list_response(p, request) for p in products]
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


# ---------------------------------------------------------------------------
# V1.2 pilot data quality endpoints (docs/v1.2-plan.md §5.4)
# ---------------------------------------------------------------------------
# These routes are intentionally registered BEFORE /{product_id} so the dynamic
# path does not shadow the static ones.
@router.get(
    "/quality-summary",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("product:view"))],
)
async def products_quality_summary(
    db: AsyncSession = Depends(get_db),
):
    """Aggregate counts per quality flag (待核价 / 缺图片 / 缺说明书 / 缺规格 ...)."""
    from app.services.quality import quality_summary

    summary = await quality_summary(db)
    return {"code": 200, "data": summary}


@router.get(
    "/quality-list",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("product:view"))],
)
async def products_quality_list(
    category_id: UUID | None = None,
    supplier_id: UUID | None = None,
    tag_ids: str | None = None,
    completeness_status: str | None = None,
    quality_flag: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Products filtered by data-quality flag (no cost/sensitive supplier cols)."""
    from app.services.quality import is_valid_quality_flag, quality_rows

    if not is_valid_quality_flag(quality_flag):
        raise HTTPException(
            status_code=422,
            detail={"code": 42206, "msg": f"quality_flag 不支持: {quality_flag}"},
        )

    series_tag_id = None
    if tag_ids:
        first = tag_ids.split(",", 1)[0].strip()
        if first:
            try:
                series_tag_id = UUID(first)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail={"code": 42201, "msg": "tag_ids 格式无效"}
                ) from exc

    rows = await quality_rows(
        db,
        completeness_status=completeness_status,
        quality_flag=quality_flag,
        supplier_id=supplier_id,
        category_id=category_id,
        series_tag_id=series_tag_id,
        limit=size,
        offset=(page - 1) * size,
    )
    return {
        "code": 200,
        "data": {"list": rows, "page": page, "size": size},
    }


@router.get(
    "/quality-export",
    dependencies=[Depends(PermissionChecker("product:export"))],
)
async def products_quality_export(
    category_id: UUID | None = None,
    supplier_id: UUID | None = None,
    tag_ids: str | None = None,
    completeness_status: str | None = None,
    quality_flag: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Excel export of the quality list. Never emits cost_price or supplier contact."""
    from app.services.quality import is_valid_quality_flag, quality_rows

    if not is_valid_quality_flag(quality_flag):
        raise HTTPException(
            status_code=422,
            detail={"code": 42206, "msg": f"quality_flag 不支持: {quality_flag}"},
        )
    series_tag_id = None
    if tag_ids:
        first = tag_ids.split(",", 1)[0].strip()
        if first:
            series_tag_id = UUID(first)

    rows = await quality_rows(
        db,
        completeness_status=completeness_status,
        quality_flag=quality_flag,
        supplier_id=supplier_id,
        category_id=category_id,
        series_tag_id=series_tag_id,
        limit=5000,
    )

    import pandas as pd

    columns = [
        "product_no",
        "product_name",
        "completeness_status",
        "face_price_label",
        "specification",
        "data_source",
        "supplier_name",
        "create_time",
        "update_time",
    ]
    df = pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)
    df = df.rename(columns={
        "product_no": "产品编号",
        "product_name": "产品名称",
        "completeness_status": "完整度状态",
        "face_price_label": "面价",
        "specification": "规格",
        "data_source": "数据来源",
        "supplier_name": "供应商",
        "create_time": "创建时间",
        "update_time": "更新时间",
    })
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="待补充清单")
    bio.seek(0)

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="quality_export.xlsx"',
            "X-Total-Count": str(len(rows)),
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
        .options(
            selectinload(Product.tags),
            joinedload(Product.brand),
            joinedload(Product.supplier),
            joinedload(Product.category),
            selectinload(Product.images).joinedload(ProductImage.attachment),
        )
        .where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})
    scene_images_data = await _fetch_scene_images_for_product(db, product_id, request)
    body = _product_response(product, request)
    body["scene_images"] = scene_images_data
    role_code = getattr(request.state, "role_code", None)
    return filter_sensitive_fields(body, role_code or "sales")


async def _fetch_scene_images_for_product(
    db: AsyncSession, product_id: UUID, request: Request
) -> list[dict]:
    result = await db.execute(
        select(product_scene_image.c.scene_image_id, product_scene_image.c.sort)
        .where(
            product_scene_image.c.product_id == product_id,
            product_scene_image.c.is_deleted.is_(False),
        )
        .order_by(product_scene_image.c.sort)
    )
    bindings = result.fetchall()
    if not bindings:
        return []

    scene_image_ids = [r.scene_image_id for r in bindings]
    sort_map = {str(r.scene_image_id): r.sort for r in bindings}

    scene_result = await db.execute(
        select(SceneImage)
        .options(joinedload(SceneImage.attachment))
        .where(
            SceneImage.id.in_(scene_image_ids),
            SceneImage.is_deleted.is_(False),
        )
    )
    scene_images = []
    for si in scene_result.scalars().all():
        if not si.attachment or si.attachment.is_deleted:
            logger.warning(
                "Skip invalid scene image: scene_image_id=%s, attachment_id=%s",
                si.id,
                si.attachment_id,
            )
            continue
        scene_images.append({
            "id": str(si.id),
            "name": si.name,
            "attachment_id": str(si.attachment_id),
            "file_url": _create_content_url(request, si.attachment_id),
            "file_name": si.attachment.file_name,
            "sort": sort_map.get(str(si.id), 0),
        })
    scene_images.sort(key=lambda image: image["sort"])
    return scene_images


def _product_response(product: Product, request: Request) -> dict:
    sorted_images = sorted(product.images, key=lambda img: img.sort)
    product_images = []
    for img in sorted_images:
        if not img.attachment or img.attachment.is_deleted:
            logger.warning(
                "Skip invalid product image: product_image_id=%s, attachment_id=%s",
                img.id,
                img.attachment_id,
            )
            continue
        product_images.append(
            {
                "id": str(img.id),
                "attachment_id": str(img.attachment_id),
                "file_url": _create_content_url(request, img.attachment_id),
                "file_name": img.attachment.file_name,
                "file_type": img.attachment.file_type,
                "sort": img.sort,
                "is_cover": img.is_cover,
            }
        )
    cover = next((img for img in product_images if img["is_cover"]), None)
    return {
        "id": str(product.id),
        "product_no": product.product_no,
        "product_name": product.product_name,
        "brand_id": str(product.brand_id),
        "supplier_id": str(product.supplier_id),
        "category_id": str(product.category_id),
        "face_price": product.face_price,
        "cost_price": product.cost_price,
        "material": product.material,
        "stock_status": product.stock_status,
        "status": product.status,
        "description": product.description,
        "specification": product.specification,
        "colors": product.colors,
        "data_source": product.data_source,
        "completeness_status": product.completeness_status,
        "tag_ids": [str(tag.id) for tag in product.tags],
        "create_time": product.create_time.isoformat(),
        "update_time": product.update_time.isoformat(),
        "brand_name": product.brand.brand_name if product.brand else None,
        "supplier_name": product.supplier.supplier_name if product.supplier else None,
        "category_name": product.category.category_name if product.category else None,
        "margin": None,
        "profit": None,
        "tags": [tag.tag_name for tag in product.tags],
        "images": product_images,
        "cover_image_id": cover["id"] if cover else None,
        "cover_image_url": cover["file_url"] if cover else None,
        "cover_image_filename": cover["file_name"] if cover else None,
        "scene_images": [],
    }


def _product_list_response(product: Product, request: Request) -> dict:
    cover = product.cover_image
    if cover and (not cover.attachment or cover.attachment.is_deleted):
        cover = None
    return {
        "id": str(product.id),
        "product_no": product.product_no,
        "product_name": product.product_name,
        "brand_id": str(product.brand_id),
        "supplier_id": str(product.supplier_id),
        "category_id": str(product.category_id),
        "face_price": product.face_price,
        "cost_price": product.cost_price,
        "material": product.material,
        "stock_status": product.stock_status,
        "status": product.status,
        "description": product.description,
        "specification": product.specification,
        "colors": product.colors,
        "data_source": product.data_source,
        "completeness_status": product.completeness_status,
        "create_time": product.create_time.isoformat(),
        "update_time": product.update_time.isoformat(),
        "brand_name": product.brand.brand_name if product.brand else None,
        "supplier_name": product.supplier.supplier_name if product.supplier else None,
        "category_name": product.category.category_name if product.category else None,
        "tags": [tag.tag_name for tag in product.tags],
        "tag_ids": [str(tag.id) for tag in product.tags],
        "cover_image_id": str(cover.id) if cover else None,
        "cover_image_url": _create_content_url(request, cover.attachment_id) if cover else None,
        "cover_image_filename": cover.attachment.file_name if cover and cover.attachment else None,
    }


# ---------------------------------------------------------------------------
# Product Image Management
# ---------------------------------------------------------------------------


class ProductImageAdd(BaseModel):
    attachment_ids: list[UUID]
    sort: int = 0


class ProductImageReorderItem(BaseModel):
    image_id: UUID
    sort: int


class ProductImageReorder(BaseModel):
    items: list[ProductImageReorderItem]


class ProductSceneImageAdd(BaseModel):
    scene_image_ids: list[UUID]


class ProductSceneImageReorderItem(BaseModel):
    scene_image_id: UUID
    sort: int


class ProductSceneImageReorder(BaseModel):
    items: list[ProductSceneImageReorderItem]


MAX_PRODUCT_IMAGES = 10
MAX_PRODUCT_SCENE_IMAGES = 30


@router.post(
    "/{product_id}/images",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("product:edit"))],
)
@audit_action("product_image_add", module="products", target_id_kwarg="product_id")
async def add_product_images(
    request: Request,
    product_id: UUID,
    data: ProductImageAdd,
    db: AsyncSession = Depends(get_db),
):
    product = await db.scalar(
        select(Product).where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})

    # Check current image count
    current_count_result = await db.execute(
        select(func.count()).select_from(ProductImage).where(
            ProductImage.product_id == product_id,
            ProductImage.is_deleted.is_(False),
        )
    )
    current_count = current_count_result.scalar() or 0

    if current_count + len(data.attachment_ids) > MAX_PRODUCT_IMAGES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": f"产品图片数量已达上限（最多 {MAX_PRODUCT_IMAGES} 张），当前 {current_count} 张，尝试添加 {len(data.attachment_ids)} 张",
            },
        )

    # Validate all attachments
    attachments = await db.scalars(
        select(Attachment).where(
            Attachment.id.in_(data.attachment_ids),
            Attachment.is_deleted.is_(False),
        )
    )
    attachment_map = {str(a.id): a for a in attachments.all()}

    for aid in data.attachment_ids:
        aid_str = str(aid)
        if aid_str not in attachment_map:
            raise HTTPException(status_code=404, detail={"code": 40401, "msg": f"附件 {aid} 不存在"})
        if attachment_map[aid_str].file_type != "image":
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "仅允许 image 类型的附件"}
            )

    # Check for duplicates
    existing_result = await db.execute(
        select(ProductImage.attachment_id).where(
            ProductImage.product_id == product_id,
            ProductImage.attachment_id.in_(data.attachment_ids),
            ProductImage.is_deleted.is_(False),
        )
    )
    existing_ids = {str(e) for e in existing_result.scalars().all()}

    added = []
    for aid in data.attachment_ids:
        aid_str = str(aid)
        if aid_str in existing_ids:
            continue

        product_image = ProductImage(
            product_id=product_id,
            attachment_id=aid,
            sort=data.sort,
            is_cover=False,
        )
        db.add(product_image)
        added.append(product_image)

    await db.commit()

    return {
        "code": 200,
        "data": {
            "added": [
                {
                    "id": str(pi.id),
                    "attachment_id": str(pi.attachment_id),
                    "sort": pi.sort,
                    "is_cover": pi.is_cover,
                }
                for pi in added
            ],
            "total": current_count + len(added),
        },
    }


@router.delete(
    "/{product_id}/images/{image_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("product:edit"))],
)
@audit_action("product_image_delete", module="products")
async def delete_product_image(
    request: Request,
    product_id: UUID,
    image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProductImage).where(
            ProductImage.id == image_id,
            ProductImage.product_id == product_id,
            ProductImage.is_deleted.is_(False),
        )
    )
    product_image = result.scalar_one_or_none()
    if not product_image:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "图片关联不存在"})

    product_image.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}


@router.patch(
    "/{product_id}/images/{image_id}/cover",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("product:edit"))],
)
@audit_action("product_image_cover", module="products")
async def set_product_cover_image(
    request: Request,
    product_id: UUID,
    image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProductImage).where(
            ProductImage.id == image_id,
            ProductImage.product_id == product_id,
            ProductImage.is_deleted.is_(False),
        )
    )
    product_image = result.scalar_one_or_none()
    if not product_image:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "图片关联不存在"})

    await db.execute(
        ProductImage.__table__.update()
        .where(
            ProductImage.product_id == product_id,
            ProductImage.is_cover.is_(True),
            ProductImage.is_deleted.is_(False),
        )
        .values(is_cover=False)
    )
    product_image.is_cover = True
    await db.commit()
    return {"code": 200, "msg": "success"}


@router.patch(
    "/{product_id}/images/reorder",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("product:edit"))],
)
@audit_action("product_image_reorder", module="products")
async def reorder_product_images(
    request: Request,
    product_id: UUID,
    data: ProductImageReorder,
    db: AsyncSession = Depends(get_db),
):
    product = await db.scalar(
        select(Product).where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})

    for item in data.items:
        await db.execute(
            ProductImage.__table__.update()
            .where(
                ProductImage.id == item.image_id,
                ProductImage.product_id == product_id,
                ProductImage.is_deleted.is_(False),
            )
            .values(sort=item.sort)
        )
    await db.commit()
    return {"code": 200, "msg": "success"}


# ---------------------------------------------------------------------------
# Product Scene Image Management
# ---------------------------------------------------------------------------


@router.post(
    "/{product_id}/scene-images",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("product:edit"))],
)
@audit_action("product_scene_image_bind", module="products", target_id_kwarg="product_id")
async def bind_product_scene_images(
    request: Request,
    product_id: UUID,
    data: ProductSceneImageAdd,
    db: AsyncSession = Depends(get_db),
):
    product = await db.scalar(
        select(Product).where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})

    # Check current scene image count for this product
    current_count_result = await db.execute(
        select(func.count())
        .select_from(product_scene_image)
        .where(
            product_scene_image.c.product_id == product_id,
            product_scene_image.c.is_deleted.is_(False),
        )
    )
    current_count = current_count_result.scalar() or 0

    if current_count + len(data.scene_image_ids) > MAX_PRODUCT_SCENE_IMAGES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": f"场景图数量已达上限（最多 {MAX_PRODUCT_SCENE_IMAGES} 张），当前 {current_count} 张，尝试添加 {len(data.scene_image_ids)} 张",
            },
        )

    # Validate all scene images
    scene_images = await db.scalars(
        select(SceneImage).where(
            SceneImage.id.in_(data.scene_image_ids),
            SceneImage.is_deleted.is_(False),
        )
    )
    scene_map = {str(s.id): s for s in scene_images.all()}

    for sid in data.scene_image_ids:
        if str(sid) not in scene_map:
            raise HTTPException(status_code=404, detail={"code": 40401, "msg": f"场景图 {sid} 不存在"})

    # Check for existing bindings and insert new ones
    bound = 0
    for sid in data.scene_image_ids:
        existing = await db.execute(
            select(product_scene_image).where(
                product_scene_image.c.product_id == product_id,
                product_scene_image.c.scene_image_id == sid,
                product_scene_image.c.is_deleted.is_(False),
            )
        )
        if existing.scalar_one_or_none():
            continue

        # 检查是否有软删除的旧记录，有则恢复而非 insert（避免组合主键冲突）
        existing_deleted = await db.execute(
            select(product_scene_image).where(
                product_scene_image.c.product_id == product_id,
                product_scene_image.c.scene_image_id == sid,
                product_scene_image.c.is_deleted.is_(True),
            )
        )
        if existing_deleted.scalar_one_or_none():
            await db.execute(
                product_scene_image.update()
                .where(
                    product_scene_image.c.product_id == product_id,
                    product_scene_image.c.scene_image_id == sid,
                )
                .values(is_deleted=False, deleted_at=None)
            )
        else:
            stmt = product_scene_image.insert().values(
                product_id=product_id,
                scene_image_id=sid,
            )
            await db.execute(stmt)
        bound += 1

    await db.commit()
    return {
        "code": 200,
        "data": {"bound": bound, "total": current_count + bound},
    }


@router.delete(
    "/{product_id}/scene-images/{scene_image_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("product:edit"))],
)
@audit_action("product_scene_image_unbind", module="products")
async def unbind_product_scene_image(
    request: Request,
    product_id: UUID,
    scene_image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    # Verify product exists
    product = await db.scalar(
        select(Product).where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})

    # Verify scene image exists
    scene_image = await db.scalar(
        select(SceneImage).where(SceneImage.id == scene_image_id, SceneImage.is_deleted.is_(False))
    )
    if not scene_image:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "场景图不存在"})

    # Soft-delete the binding (not the scene image itself)
    await db.execute(
        product_scene_image.update()
        .where(
            product_scene_image.c.product_id == product_id,
            product_scene_image.c.scene_image_id == scene_image_id,
        )
        .values(is_deleted=True)
    )
    await db.commit()
    return {"code": 200, "msg": "success"}


@router.patch(
    "/{product_id}/scene-images/reorder",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("product:edit"))],
)
@audit_action("product_scene_image_reorder", module="products")
async def reorder_product_scene_images(
    request: Request,
    product_id: UUID,
    data: ProductSceneImageReorder,
    db: AsyncSession = Depends(get_db),
):
    product = await db.scalar(
        select(Product).where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    if not product:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "产品不存在"})

    for item in data.items:
        await db.execute(
            product_scene_image.update()
            .where(
                product_scene_image.c.product_id == product_id,
                product_scene_image.c.scene_image_id == item.scene_image_id,
                product_scene_image.c.is_deleted.is_(False),
            )
            .values(sort=item.sort)
        )
    await db.commit()
    return {"code": 200, "msg": "success"}


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
    product = await db.scalar(
        select(Product)
        .options(
            selectinload(Product.tags),
            selectinload(Product.brand),
            selectinload(Product.supplier),
            selectinload(Product.category),
            selectinload(Product.images).joinedload(ProductImage.attachment),
        )
        .where(Product.id == product.id)
    )
    return _product_response(product, request)


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    dependencies=[Depends(PermissionChecker("product:edit"))],
)
async def update_product(
    request: Request,
    product_id: UUID,
    product_data: ProductUpdate,
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

    values = product_data.model_dump(exclude_unset=True)
    tag_ids = values.pop("tag_ids", None)
    next_face_price = values.get("face_price", product.face_price)
    next_completeness = values.get("completeness_status", product.completeness_status)
    if next_face_price == 99999 and next_completeness != "pending":
        raise HTTPException(
            status_code=422,
            detail={"code": 42205, "msg": "占位面价 99999 仅允许用于待补充产品"},
        )
    for field, value in values.items():
        setattr(product, field, value)

    if tag_ids is not None:
        await db.execute(
            ProductTag.__table__.delete().where(ProductTag.product_id == product.id)
        )
        for tag_id in tag_ids:
            db.add(ProductTag(product_id=product.id, tag_id=tag_id))

    await db.commit()
    product = await db.scalar(
        select(Product)
        .options(
            selectinload(Product.tags),
            selectinload(Product.brand),
            selectinload(Product.supplier),
            selectinload(Product.category),
            selectinload(Product.images).joinedload(ProductImage.attachment),
        )
        .where(Product.id == product.id)
    )
    return _product_response(product, request)


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
        specification=product.specification,
        colors=product.colors,
        description=product.description,
        data_source=product.data_source,
        completeness_status=product.completeness_status,
        stock_status=product.stock_status,
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
