import asyncio
import datetime
import io
import logging
import os
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.minio_client import get_minio_client
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
from app.services.excel_images import extract_embedded_images
from app.services.product_import import (
    ProductRow,
    RowFields,
    SheetError,
    build_import_template,
    parse_row,
    read_product_sheet,
)
from app.services.product_import_media import (
    ROLE_MAIN,
    ROLE_SCENE,
    MediaError,
    MediaResolver,
    MediaUploader,
    fetch_image_url,
    load_bundle,
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

    query = (
        select(Product)
        .options(
            selectinload(Product.tags),
            joinedload(Product.brand),
            joinedload(Product.supplier),
            joinedload(Product.category),
            selectinload(Product.images).joinedload(ProductImage.attachment),
        )
        .where(Product.is_deleted.is_(False))
    )

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
        tag_keyword_subq = (
            select(ProductTag.product_id)
            .join(Tag, ProductTag.tag_id == Tag.id)
            .where(
                Tag.tag_name.ilike(f"%{keyword}%"),
                Tag.is_deleted.is_(False),
            )
        )
        query = query.where(
            (Product.product_name.ilike(f"%{keyword}%"))
            | (Product.product_no.ilike(f"%{keyword}%"))
            | (Product.id.in_(tag_keyword_subq))
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


# 同样要排在 /{product_id} 之前。
@router.get("/import-template", dependencies=[Depends(PermissionChecker("product:import"))])
async def download_import_template():
    """下载批量导入模板（列名和导出一致，另附「填写说明」页讲三种给图方式）。

    Import.vue 里一直写着「请下载模板文件」却没有下载入口，用户只能照页面上那段
    中文说明猜列名。模板由 services/product_import.build_import_template 生成，
    tests/unit/test_product_import.py 有一条用例保证它能被本项目的导入器读回来。
    """
    payload = build_import_template()

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="products_import_template.xlsx"',
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
    df = df.rename(
        columns={
            "product_no": "产品编号",
            "product_name": "产品名称",
            "completeness_status": "完整度状态",
            "face_price_label": "面价",
            "specification": "规格",
            "data_source": "数据来源",
            "supplier_name": "供应商",
            "create_time": "创建时间",
            "update_time": "更新时间",
        }
    )
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
        scene_images.append(
            {
                "id": str(si.id),
                "name": si.name,
                "attachment_id": str(si.attachment_id),
                "file_url": _create_content_url(request, si.attachment_id),
                "file_name": si.attachment.file_name,
                "sort": sort_map.get(str(si.id), 0),
            }
        )
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
        select(func.count())
        .select_from(ProductImage)
        .where(
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
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": f"附件 {aid} 不存在"}
            )
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
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": f"场景图 {sid} 不存在"}
            )

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
        select(Product)
        .options(selectinload(Product.tags))
        .where(Product.product_no == product_data.product_no, Product.is_deleted.is_(False))
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
        await db.execute(ProductTag.__table__.delete().where(ProductTag.product_id == product.id))
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


# ---------------------------------------------------------------------------
# 批量导入（表格 + 图片）
# ---------------------------------------------------------------------------
# 拆成三层：services/product_import.py 认表头和解析行，
# services/excel_images.py 抠内嵌图片，services/product_import_media.py 决定图片
# 归哪一行、上传到对象存储。这里只做「查库 + 写库」，所以上面那三层能在
# tests/unit 里被单独钉住（归属算错时图会挂到相邻产品身上，是最难发现的一类错）。

# 导入结果里最多回显多少条提示。两千行的表能攒出几千条降级提示，全塞进 JSON 会把
# 响应撑到几 MB，前端表格也没法看。
_MAX_REPORTED_NOTES = 200


def _capped(items: list[str]) -> list[str]:
    if len(items) <= _MAX_REPORTED_NOTES:
        return items
    return [*items[:_MAX_REPORTED_NOTES], f"…另有 {len(items) - _MAX_REPORTED_NOTES} 条提示未显示"]


def _url_fetcher(*, timeout: float, max_bytes: int) -> Callable[[str], tuple[bytes, str]]:
    """图片直链的抓取器（默认关闭，见 settings.PRODUCT_IMPORT_ALLOW_URL_FETCH）。

    fetch_image_url 内部先把域名解析成 IP 并要求是公网地址，重定向逐跳复查 —— 服务端
    替用户 GET 任意地址就是 SSRF，云上的元数据接口（169.254.169.254）是现成的目标。
    """

    def fetch(url: str) -> tuple[bytes, str]:
        return fetch_image_url(url, timeout=timeout, max_bytes=max_bytes)

    return fetch


async def _name_to_id(
    db: AsyncSession, model: Any, column: Any, names: set[str]
) -> dict[str, UUID]:
    """名字 → 主键。一次查完，避免每行一条 SELECT。

    分类名在库里不唯一（不同父级下可以同名），按 create_time 排序后取第一条：同一份
    表重导两次至少落到同一个分类上，随机挑一个会让两次导入的归属不一致。
    """
    if not names:
        return {}
    result = await db.execute(
        select(column, model.id)
        .where(column.in_(names), model.is_deleted.is_(False))
        .order_by(model.create_time)
    )
    out: dict[str, UUID] = {}
    for name, ident in result.all():
        out.setdefault(name, ident)
    return out


def _db_failure_reason(exc: Exception) -> str:
    """行级失败原因。原始 SQL 报错既看不懂也可能回显库结构，只给能行动的那句。"""
    if isinstance(exc, IntegrityError):
        return "违反数据库约束（编号重复或枚举值不合法），已跳过该行"
    return f"写入数据库失败（{type(exc).__name__}），已跳过该行"


def _ingest_row_media(
    resolver: MediaResolver,
    uploader: MediaUploader,
    rows: list[tuple[ProductRow, str]],
) -> tuple[dict[int, dict[str, Any]], list[str], set[str]]:
    """在线程里跑完「图片归属 → 取字节 → 传对象存储」，返回每行该绑的图。

    minio 客户端和 httpx 都是同步阻塞的：两百张图直接在事件循环里传会把整个进程堵住
    十几秒，同时在线的其他请求全部排队。所以这段整体放进 asyncio.to_thread。

    一张图传不上去只影响那一张，记条提示继续 —— 图能事后补，为它回滚整份导入不值得。
    """
    per_row: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []
    sources: set[str] = set()
    for row, product_no in rows:
        media = resolver.resolve(row, product_no=product_no)
        warnings.extend(media.warnings)
        bucket: dict[str, Any] = {"cover": None, "images": [], "scenes": []}
        for blob in media.blobs:
            try:
                uploaded = uploader.upload(blob)
            except MediaError as exc:
                warnings.append(f"第 {row.excel_row} 行：{exc}")
                continue
            sources.add(blob.source)
            if blob.role == ROLE_MAIN:
                bucket["cover"] = uploaded
            elif blob.role == ROLE_SCENE:
                bucket["scenes"].append(uploaded)
            else:
                bucket["images"].append(uploaded)
        per_row[row.excel_row] = bucket
    return per_row, warnings, sources


@router.post("/import", dependencies=[Depends(PermissionChecker("product:import"))])
@audit_action("product_import", module="products")
async def import_products(
    request: Request,
    file: UploadFile = File(...),
    skip_if_exists: bool = Query(False, alias="skipIfExists"),
    db: AsyncSession = Depends(get_db),
):
    """批量导入产品，连产品图和场景图一起导。

    收三种给图方式（都在 tests/unit/test_product_import_media.py 里钉着）：

    1. 图片贴在表格里（浮动图片 / WPS 的 DISPIMG / M365 的「置于单元格内」）——
       按图片落在哪一行哪一列决定归属：主图列→封面，产品图列→产品图，场景图列→场景图；
    2. 上传一个 zip：表格 + 图片文件，格子里写文件名，或者干脆把文件名以产品编号开头
       （SUNON-001-1.jpg），后者只在这一行没写任何图片名时才启用；
    3. 格子里写 http(s) 直链 —— 默认关闭（SSRF），要开见
       settings.PRODUCT_IMPORT_ALLOW_URL_FETCH。

    写库分两段：先把图片对象和 attachment/scene_image 落下来（同一 sha256 全批只传一次、
    只建一条 attachment），再按行开 SAVEPOINT 建产品。老实现是整批一次 commit，一行撞
    约束就把前面几百行一起带走；现在一行失败只回滚那一行，其余照常入库。
    """
    # UploadFile 的底层就是个临时文件（Starlette 超过 1MB 就落盘），所以体积用 seek
    # 量、字节交给 load_bundle 按需读：一个 259MB 的包不该先在内存里躺成一份 bytes，
    # 再由 zipfile 解成第二份几百兆。
    upload = file.file
    upload.seek(0, os.SEEK_END)
    size = upload.tell()
    upload.seek(0)
    if size > settings.PRODUCT_IMPORT_MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 40004,
                "msg": f"上传 {size} 字节，超过上限 "
                f"{settings.PRODUCT_IMPORT_MAX_FILE_BYTES} 字节，请拆成多份导入",
            },
        )

    # 上传的可能是裸 xlsx，也可能是「表格 + 图片」的 zip。xlsx 自己就是 zip，所以
    # load_bundle 是靠里面有没有 xl/workbook.xml 区分的。
    try:
        bundle = load_bundle(
            upload,
            max_image_bytes=settings.PRODUCT_IMPORT_MAX_IMAGE_BYTES,
            max_total_bytes=settings.PRODUCT_IMPORT_MAX_FILE_BYTES,
        )
    except MediaError as exc:
        raise HTTPException(status_code=400, detail={"code": 40003, "msg": str(exc)}) from exc

    # zip 包在整段取图期间都开着（成员是按需读的），所以下面无论从哪儿退出都要关掉它：
    # 请求一结束 UploadFile 就没了，不能留着还能去读它的 loader。
    try:
        try:
            sheet = read_product_sheet(bundle.xlsx)
        except SheetError as exc:
            raise HTTPException(
                status_code=400, detail={"code": 40001, "msg": str(exc)}
            ) from exc

        if len(sheet.rows) > settings.PRODUCT_IMPORT_MAX_ROWS:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40004,
                    "msg": f"表里有 {len(sheet.rows)} 行数据，超过单次上限 "
                    f"{settings.PRODUCT_IMPORT_MAX_ROWS} 行，请拆分后导入",
                },
            )

        notes: list[str] = list(sheet.warnings)
        image_warnings: list[str] = list(bundle.warnings)
        if sheet.unknown_headers:
            notes.append("这些列没认出来，已忽略：" + "、".join(sheet.unknown_headers))

        # 内嵌图片解析失败不该让整份表进不来：表格文字部分照常导，图片那部分给条提示。
        embedded = []
        try:
            extracted = await asyncio.to_thread(
                extract_embedded_images,
                bundle.xlsx,
                max_image_bytes=settings.PRODUCT_IMPORT_MAX_IMAGE_BYTES,
            )
        except Exception:  # noqa: BLE001 - 任何解析异常都降级，原因写日志
            logger.warning("批量导入：内嵌图片解析失败", exc_info=True)
            image_warnings.append("表格里的内嵌图片没解析成功，本次只按文件名/直链导入图片")
        else:
            embedded = extracted.images
            image_warnings.extend(extracted.warnings)

        parsed = [parse_row(row) for row in sheet.rows]
        brand_map = await _name_to_id(
            db, Brand, Brand.brand_name, {f.brand_name for f in parsed if f.brand_name}
        )
        supplier_map = await _name_to_id(
            db,
            Supplier,
            Supplier.supplier_name,
            {f.supplier_name for f in parsed if f.supplier_name},
        )
        # 分类名在库里不唯一（不同父级下可以同名），这里取创建最早的那个。
        category_map = await _name_to_id(
            db,
            Category,
            Category.category_name,
            {f.category_name for f in parsed if f.category_name},
        )
        tag_map = await _name_to_id(db, Tag, Tag.tag_name, {t for f in parsed for t in f.tag_names})

        # 编号查重一次查完。老实现是每行一条 SELECT，两千行就是两千个来回。
        taken: set[str] = set()
        wanted = {f.product_no for f in parsed if f.product_no}
        if wanted:
            found = await db.execute(
                select(Product.product_no).where(
                    Product.product_no.in_(wanted), Product.is_deleted.is_(False)
                )
            )
            taken = {value for (value,) in found.all()}

        # 先把「这行能不能进库」判完，再去动图片：解析不了的行没必要为它下载/上传图片。
        failures: list[dict[str, Any]] = []
        todo: list[tuple[ProductRow, RowFields, dict[str, UUID]]] = []
        missing_tags: set[str] = set()
        seen: set[str] = set()
        for row, fields in zip(sheet.rows, parsed, strict=True):
            reasons = list(fields.errors)
            refs: dict[str, UUID] = {}
            if not reasons:
                if fields.product_no in seen:
                    reasons.append("表里有重复的产品编号，只导入第一次出现的那行")
                elif fields.product_no in taken:
                    reasons.append("编号已存在，已跳过" if skip_if_exists else "产品编号已存在")
                # brand_id/supplier_id/category_id 在库里都是 NOT NULL，缺一个这行就进不去。
                # 主数据由各自的管理页维护，导入不替用户新建：一个错别字凭空造出个品牌，
                # 比这行导不进去更难收拾。
                for label, name, mapping, key in (
                    ("品牌", fields.brand_name, brand_map, "brand_id"),
                    ("供应商", fields.supplier_name, supplier_map, "supplier_id"),
                    ("分类", fields.category_name, category_map, "category_id"),
                ):
                    if not name:
                        reasons.append(f"{label}为空（产品必须挂在{label}下）")
                        continue
                    ident = mapping.get(name)
                    if ident is None:
                        reasons.append(f"{label}「{name}」系统里没有，请先建好再导入")
                    else:
                        refs[key] = ident
            if reasons:
                failures.append(
                    {
                        "row": row.excel_row,
                        "product_no": fields.product_no,
                        "reason": "；".join(reasons),
                    }
                )
                continue
            seen.add(fields.product_no)
            missing_tags.update(name for name in fields.tag_names if name not in tag_map)
            notes.extend(f"第 {fields.excel_row} 行：{note}" for note in fields.notes)
            todo.append((row, fields, refs))

        if missing_tags:
            notes.append("这些标签系统里没有，已忽略：" + "、".join(sorted(missing_tags)))

        uploaded_count = 0
        sources: set[str] = set()
        per_row: dict[int, dict[str, Any]] = {}
        if todo:
            resolver = MediaResolver(
                sheet,
                embedded=embedded,
                bundle=bundle,
                url_fetcher=(
                    _url_fetcher(
                        timeout=settings.PRODUCT_IMPORT_URL_TIMEOUT,
                        max_bytes=settings.PRODUCT_IMPORT_MAX_IMAGE_BYTES,
                    )
                    if settings.PRODUCT_IMPORT_ALLOW_URL_FETCH
                    else None
                ),
                # 每行的上限不能超过 /images 接口的上限，否则导进来的产品一打开就是「已达上限」。
                max_images=min(settings.PRODUCT_IMPORT_MAX_IMAGES_PER_ROW, MAX_PRODUCT_IMAGES),
                max_scenes=min(
                    settings.PRODUCT_IMPORT_MAX_SCENES_PER_ROW, MAX_PRODUCT_SCENE_IMAGES
                ),
                max_image_bytes=settings.PRODUCT_IMPORT_MAX_IMAGE_BYTES,
            )
            image_warnings.extend(resolver.warnings)
            uploader = MediaUploader(get_minio_client(), settings.MINIO_BUCKET)
            per_row, media_warnings, sources = await asyncio.to_thread(
                _ingest_row_media,
                resolver,
                uploader,
                [(row, fields.product_no) for row, fields, _ in todo],
            )
            image_warnings.extend(media_warnings)
            uploaded_count = uploader.uploaded
    finally:
        # 图片已经全部读完并传到对象存储，后面只动数据库，zip 可以撒手了。
        bundle.close()

    # 同一 sha256 全批只建一条 attachment：一张品牌形象场景图被三十行引用时，对象存储里
    # 只存一份，三十个产品共用它（product_scene_image 本来就是多对多）。
    attachments: dict[str, Attachment] = {}
    for buckets in per_row.values():
        cover = buckets["cover"]
        gallery = [cover] if cover is not None else []
        for obj in [*gallery, *buckets["images"], *buckets["scenes"]]:
            attachments.setdefault(
                obj.sha256,
                Attachment(
                    file_name=obj.name,
                    file_url=obj.file_url,
                    file_type="image",
                    file_size=obj.size,
                    storage_type="minio",
                    oss_key=obj.oss_key,
                ),
            )
    if attachments:
        db.add_all(attachments.values())
        await db.flush()

    scene_images: dict[str, SceneImage] = {}
    for buckets in per_row.values():
        for obj in buckets["scenes"]:
            scene_images.setdefault(
                obj.sha256,
                SceneImage(name=obj.name[:128], attachment_id=attachments[obj.sha256].id),
            )
    if scene_images:
        db.add_all(scene_images.values())
        await db.flush()

    empty: dict[str, Any] = {"cover": None, "images": [], "scenes": []}
    success = 0
    image_count = 0
    scene_count = 0
    for row, fields, refs in todo:
        buckets = per_row.get(row.excel_row, empty)
        cover = buckets["cover"]
        gallery = ([cover] if cover is not None else []) + buckets["images"]
        scenes = buckets["scenes"]
        # 一行一个 SAVEPOINT：撞了约束只回滚这一行，前面已经建好的产品照常保留。
        try:
            async with db.begin_nested():
                product = Product(
                    product_no=fields.product_no,
                    product_name=fields.product_name,
                    brand_id=refs["brand_id"],
                    supplier_id=refs["supplier_id"],
                    category_id=refs["category_id"],
                    face_price=fields.face_price,
                    cost_price=fields.cost_price,
                    material=fields.material,
                    specification=fields.specification,
                    colors=fields.colors,
                    description=fields.description,
                    data_source=fields.data_source,
                    stock_status=fields.stock_status,
                    status=fields.status,
                    completeness_status=fields.completeness_status,
                )
                db.add(product)
                await db.flush()
                for tag_name in fields.tag_names:
                    tag_id = tag_map.get(tag_name)
                    if tag_id is not None:
                        db.add(ProductTag(product_id=product.id, tag_id=tag_id))
                for index, obj in enumerate(gallery):
                    db.add(
                        ProductImage(
                            product_id=product.id,
                            attachment_id=attachments[obj.sha256].id,
                            sort=index,
                            is_cover=index == 0,
                        )
                    )
                for index, obj in enumerate(scenes):
                    await db.execute(
                        product_scene_image.insert().values(
                            product_id=product.id,
                            scene_image_id=scene_images[obj.sha256].id,
                            sort=index,
                        )
                    )
                await db.flush()
        except SQLAlchemyError as exc:
            logger.warning("批量导入第 %s 行入库失败", row.excel_row, exc_info=True)
            failures.append(
                {
                    "row": row.excel_row,
                    "product_no": fields.product_no,
                    "reason": _db_failure_reason(exc),
                }
            )
            continue
        success += 1
        image_count += len(gallery)
        scene_count += len(scenes)

    await db.commit()
    failures.sort(key=lambda item: item["row"])

    return {
        "code": 200,
        "data": {
            "total": len(sheet.rows),
            "success_count": success,
            "fail_count": len(failures),
            "failures": failures,
            "notes": _capped(notes),
            "image_count": image_count,
            "scene_image_count": scene_count,
            "uploaded_count": uploaded_count,
            "image_sources": sorted(sources),
            "image_warnings": _capped(image_warnings),
            "header_row": sheet.header_row,
            "unknown_headers": sheet.unknown_headers,
            "blank_rows": sheet.blank_rows,
        },
    }
