import asyncio
import datetime
import io
import logging
import os
import re
import time
import unicodedata
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
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
from app.services.import_staging import (
    StagingError,
    cleanup_expired,
    consume_staged,
    discard_staged,
    load_staged,
    stage_upload,
    update_staged_meta,
)
from app.services.product_import import (
    PLACEHOLDER_PRICE,
    ProductRow,
    RowFields,
    SheetError,
    build_import_template,
    parse_row,
    read_product_sheet,
)
from app.services.product_import_backup import write_import_backup
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
                query.join(
                    ProductTag,
                    (ProductTag.product_id == Product.id)
                    & (ProductTag.is_deleted.is_(False)),
                )
                .where(ProductTag.tag_id.in_(parsed_tag_ids))
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

    # 计算总数时只数子查询中的 Product.id。不能在 select_from(query.subquery())
    # 外再引用 Product.id，否则 SQLAlchemy 会把原始 product 表再次放进 FROM，
    # 造成笛卡尔积并使筛选后的 total 不可信。
    product_rows = query.subquery()
    total_result = await db.execute(
        select(func.count(func.distinct(product_rows.c.id))).select_from(product_rows)
    )
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
                "msg": (
                    f"产品图片数量已达上限（最多 {MAX_PRODUCT_IMAGES} 张），"
                    f"当前 {current_count} 张，尝试添加 {len(data.attachment_ids)} 张"
                ),
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
                "msg": (
                    f"场景图数量已达上限（最多 {MAX_PRODUCT_SCENE_IMAGES} 张），"
                    f"当前 {current_count} 张，尝试添加 {len(data.scene_image_ids)} 张"
                ),
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


IMPORT_MODES = frozenset({"create", "overwrite", "append", "skip"})

# 预检暂存目录的清理节流（秒）。只影响失效 token 的磁盘回收，不影响正确性。
_STAGING_CLEANUP_INTERVAL = 3600
_staging_cleaned_at = 0.0


def _maybe_cleanup_staging() -> None:
    global _staging_cleaned_at
    now = time.time()
    if now - _staging_cleaned_at < _STAGING_CLEANUP_INTERVAL:
        return
    _staging_cleaned_at = now
    try:
        cleanup_expired()
    except OSError:
        logger.warning("清理导入预检暂存失败", exc_info=True)

# RowFields.provided 里「直接写回 Product 列」的字段
_IMPORT_WRITABLE_FIELDS = (
    "product_name",
    "face_price",
    "cost_price",
    "material",
    "specification",
    "colors",
    "description",
    "data_source",
    "stock_status",
    "status",
    "completeness_status",
)


def _apply_product_fields(
    product: Product, fields: RowFields, refs: dict[str, UUID], mode: str
) -> None:
    """把表格字段合并进现有产品。

    * 只处理 ``fields.provided`` 里的字段 —— 单元格空着不等于「清空」；
    * 追加模式只在库里为空时写，已有非空值一律不动；
    * 面价写占位价 99999 时必须同时把完整度改成 pending，否则撞
      ``check_product_placeholder_price``；反过来写了真实价格就把悬挂的
      「待补充」恢复成 complete（除非表格自己指定了完整度）。
    """
    for field in _IMPORT_WRITABLE_FIELDS:
        if field not in fields.provided:
            continue
        value = getattr(fields, field)
        if mode == "append" and getattr(product, field) not in (None, ""):
            continue
        setattr(product, field, value)
        if field == "face_price":
            if value == PLACEHOLDER_PRICE:
                product.completeness_status = "pending"
            elif "completeness_status" not in fields.provided:
                product.completeness_status = "complete"

    for key in ("brand_id", "supplier_id", "category_id"):
        ident = refs.get(key)
        if ident is None:
            continue
        if mode == "append" and getattr(product, key):
            continue
        setattr(product, key, ident)


async def _existing_tag_ids(db: AsyncSession, product_id: UUID) -> set[UUID]:
    rows = (
        await db.execute(
            select(ProductTag.tag_id).where(
                ProductTag.product_id == product_id, ProductTag.is_deleted.is_(False)
            )
        )
    ).scalars().all()
    return set(rows)


async def _replace_product_tags(
    db: AsyncSession,
    product: Product,
    fields: RowFields,
    tag_index: tuple[dict[tuple[str, str], UUID], dict[str, list[UUID]]],
) -> None:
    """标签整组替换：表格没写标签列就不动，写了就按表格内容重建。"""
    if "tag_names" not in fields.provided:
        return
    await db.execute(
        sa_update(ProductTag)
        .where(ProductTag.product_id == product.id, ProductTag.is_deleted.is_(False))
        .values(is_deleted=True, deleted_at=func.now())
    )
    for tag_name, type_hint in fields.tag_specs:
        tag_id = _resolve_tag_id(tag_index, tag_name, type_hint)
        if tag_id is not None:
            db.add(ProductTag(product_id=product.id, tag_id=tag_id))


async def _append_product_tags(
    db: AsyncSession,
    product: Product,
    fields: RowFields,
    tag_index: tuple[dict[tuple[str, str], UUID], dict[str, list[UUID]]],
) -> None:
    if not fields.tag_specs:
        return
    current = await _existing_tag_ids(db, product.id)
    for tag_name, type_hint in fields.tag_specs:
        tag_id = _resolve_tag_id(tag_index, tag_name, type_hint)
        if tag_id is not None and tag_id not in current:
            db.add(ProductTag(product_id=product.id, tag_id=tag_id))
            current.add(tag_id)


async def _replace_product_images(
    db: AsyncSession, product: Product, gallery: list, attachments: dict
) -> int:
    """整套替换产品图；这一行没解析到图时保留原图（空表不等于删图）。"""
    if not gallery:
        return 0
    await db.execute(
        sa_update(ProductImage)
        .where(ProductImage.product_id == product.id, ProductImage.is_deleted.is_(False))
        .values(is_deleted=True, deleted_at=func.now())
    )
    for index, obj in enumerate(gallery):
        db.add(
            ProductImage(
                product_id=product.id,
                attachment_id=attachments[obj.sha256].id,
                sort=index,
                is_cover=index == 0,
            )
        )
    return len(gallery)


async def _append_product_images(
    db: AsyncSession, product: Product, gallery: list, attachments: dict
) -> int:
    """只增不减：按 attachment 去重，原本没有封面才把第一张新图设成封面。"""
    if not gallery:
        return 0
    rows = (
        await db.execute(
            select(ProductImage.attachment_id, ProductImage.is_cover, ProductImage.sort).where(
                ProductImage.product_id == product.id, ProductImage.is_deleted.is_(False)
            )
        )
    ).all()
    existing = {row.attachment_id for row in rows}
    has_cover = any(row.is_cover for row in rows)
    next_sort = max((row.sort or 0 for row in rows), default=-1) + 1
    added = 0
    for obj in gallery:
        attachment_id = attachments[obj.sha256].id
        if attachment_id in existing:
            continue
        db.add(
            ProductImage(
                product_id=product.id,
                attachment_id=attachment_id,
                sort=next_sort + added,
                is_cover=not has_cover and added == 0,
            )
        )
        existing.add(attachment_id)
        added += 1
    return added


async def _scene_bindings(db: AsyncSession, product_id: UUID) -> dict[UUID, tuple[int, bool]]:
    """product_scene_image 的主键是 (product_id, scene_image_id)，软删除行也在表里。

    所以「重新绑定」不能直接 INSERT —— 同一对主键会撞 PK，必须把软删除行恢复。
    """
    rows = (
        await db.execute(
            select(
                product_scene_image.c.scene_image_id,
                product_scene_image.c.sort,
                product_scene_image.c.is_deleted,
            ).where(product_scene_image.c.product_id == product_id)
        )
    ).all()
    return {
        row.scene_image_id: (row.sort or 0, bool(row.is_deleted))
        for row in rows
    }


async def _bind_scene(
    db: AsyncSession, product_id: UUID, scene_image_id: UUID, *, sort: int, known: bool
) -> None:
    if known:
        await db.execute(
            product_scene_image.update()
            .where(
                product_scene_image.c.product_id == product_id,
                product_scene_image.c.scene_image_id == scene_image_id,
            )
            .values(is_deleted=False, deleted_at=None, sort=sort)
        )
        return
    await db.execute(
        product_scene_image.insert().values(
            product_id=product_id, scene_image_id=scene_image_id, sort=sort
        )
    )


async def _replace_product_scenes(
    db: AsyncSession, product: Product, scenes: list, scene_images: dict
) -> None:
    if not scenes:
        return
    bindings = await _scene_bindings(db, product.id)
    desired = [scene_images[obj.sha256].id for obj in scenes]
    for index, scene_image_id in enumerate(desired):
        await _bind_scene(
            db, product.id, scene_image_id, sort=index, known=scene_image_id in bindings
        )
    keep = set(desired)
    for scene_image_id, (_sort, is_deleted) in bindings.items():
        if scene_image_id in keep or is_deleted:
            continue
        await db.execute(
            product_scene_image.update()
            .where(
                product_scene_image.c.product_id == product.id,
                product_scene_image.c.scene_image_id == scene_image_id,
            )
            .values(is_deleted=True, deleted_at=func.now())
        )


async def _append_product_scenes(
    db: AsyncSession, product: Product, scenes: list, scene_images: dict
) -> int:
    if not scenes:
        return 0
    bindings = await _scene_bindings(db, product.id)
    active = {key for key, (_sort, is_deleted) in bindings.items() if not is_deleted}
    next_sort = max((sort for sort, _ in bindings.values()), default=-1) + 1
    added = 0
    for obj in scenes:
        scene_image_id = scene_images[obj.sha256].id
        if scene_image_id in active:
            continue
        await _bind_scene(
            db, product.id, scene_image_id, sort=next_sort + added, known=scene_image_id in bindings
        )
        active.add(scene_image_id)
        added += 1
    return added


def _tag_type_key(tag_type: str | None) -> str:
    return (tag_type or "").strip().lower()


async def _load_tag_index(
    db: AsyncSession,
) -> tuple[dict[tuple[str, str], UUID], dict[str, list[UUID]]]:
    """标签查找表：先按 (名称, 类型) 精确命中，再按名称兜底。

    名称兜底是有意为之：表格里只写「摩耳」而库里已有同名 series 标签时，应当
    复用那一条，而不是再建一个无类型的同名标签。
    """
    rows = (
        await db.execute(
            select(Tag.id, Tag.tag_name, Tag.tag_type)
            .where(Tag.is_deleted.is_(False))
            .order_by(Tag.create_time, Tag.id)
        )
    ).all()
    by_key: dict[tuple[str, str], UUID] = {}
    by_name: dict[str, list[UUID]] = {}
    for row in rows:
        by_key[(row.tag_name, _tag_type_key(row.tag_type))] = row.id
        by_name.setdefault(row.tag_name, []).append(row.id)
    return by_key, by_name


def _resolve_tag_id(
    index: tuple[dict[tuple[str, str], UUID], dict[str, list[UUID]]],
    name: str,
    type_hint: str | None,
) -> UUID | None:
    by_key, by_name = index
    if type_hint is not None:
        return by_key.get((name, _tag_type_key(type_hint)))
    ids = by_name.get(name)
    return ids[0] if ids else None


def _normalize_new_tag_type(raw: str | None) -> str | None:
    """导入参数里的「新标签类型」：series 或 none（空 = 不分组）。"""
    value = (raw or "").strip().lower()
    if value in {"", "none", "null", "no", "off"}:
        return None
    return value if re.fullmatch(r"[a-z][a-z0-9_-]{0,15}", value) else "series"


# ---------------------------------------------------------------------------
# 产品编号别名：103800022 ↔ P-103800022
#
# 生产里同一个产品被先后录成了带前缀与不带前缀两条，只看精确 product_no 会让
# 「覆盖」变成新建第二条。这里只识别「前导 P- 与无前导 P-」这一种关系：比较时
# 忽略大小写与首尾空格，但绝不改写库里实际存储的编号。
# ---------------------------------------------------------------------------
_PRODUCT_NO_ALIAS_PREFIX = "p-"
ALIAS_ACTIONS = frozenset({"overwrite_alias", "create_new"})
ALIAS_RISK_SAFE = "safe"
ALIAS_RISK_HIGH = "high"


def _normalize_product_no(value: str | None) -> str:
    """仅用于比较的产品编号键：去首尾空格 + 忽略大小写。"""
    return (value or "").strip().casefold()


def _product_no_alias_key(value: str | None) -> str:
    """别名比较键：在 ``_normalize_product_no`` 之上再去掉前导 ``P-``。"""
    key = _normalize_product_no(value)
    if key.startswith(_PRODUCT_NO_ALIAS_PREFIX):
        key = key[len(_PRODUCT_NO_ALIAS_PREFIX) :].strip()
    return key


def _normalize_product_name(value: str | None) -> str:
    """产品名称规范化：全角转半角、忽略大小写与所有空白。"""
    return "".join(unicodedata.normalize("NFKC", value or "").casefold().split())


async def _alias_products_by_key(
    db: AsyncSession, alias_keys: set[str]
) -> dict[str, list[Product]]:
    """按别名键取候选产品（含已软删除，用于把「已删除」判成高风险）。

    用 ``lower(trim(product_no))`` 在库里做一次粗筛，再在 Python 里按别名键精确
    归类；这样既能容忍存储侧的空白/大小写差异，又不需要为编号建函数索引。
    """
    if not alias_keys:
        return {}
    variants = set(alias_keys) | {_PRODUCT_NO_ALIAS_PREFIX + key for key in alias_keys}
    result = await db.execute(
        select(Product)
        .where(func.lower(func.trim(Product.product_no)).in_(variants))
        .order_by(Product.create_time, Product.id)
    )
    grouped: dict[str, list[Product]] = {}
    for product in result.scalars().all():
        key = _product_no_alias_key(product.product_no)
        if key in alias_keys:
            grouped.setdefault(key, []).append(product)
    return grouped


def _classify_alias(
    fields: RowFields, candidates: list[Product]
) -> dict[str, Any] | None:
    """判断一行与现有产品的别名关系。没有候选返回 None。

    只有「候选唯一、未删除、名称规范化后相同」才算安全；其余一律高风险，
    绝不允许自动覆盖。
    """
    if not candidates:
        return None
    deleted = [product for product in candidates if product.is_deleted]
    active = [product for product in candidates if not product.is_deleted]
    numbers = "、".join(product.product_no for product in candidates)
    if deleted:
        return {
            "risk": ALIAS_RISK_HIGH,
            "reason": f"别名编号对应的产品已删除（{numbers}），不能自动覆盖",
            "product": deleted[0] if len(candidates) == 1 else None,
            "candidate_numbers": numbers,
        }
    if len(active) != 1:
        return {
            "risk": ALIAS_RISK_HIGH,
            "reason": f"别名候选不唯一（{len(active)} 个：{numbers}），不能自动覆盖",
            "product": None,
            "candidate_numbers": numbers,
        }
    product = active[0]
    incoming_name = _normalize_product_name(fields.product_name)
    existing_name = _normalize_product_name(product.product_name)
    if not incoming_name or incoming_name != existing_name:
        return {
            "risk": ALIAS_RISK_HIGH,
            "reason": (
                f"名称不一致（表内「{fields.product_name or ''}」/ "
                f"系统内「{product.product_name or ''}」），不能自动覆盖"
            ),
            "product": product,
            "candidate_numbers": product.product_no,
        }
    return {
        "risk": ALIAS_RISK_SAFE,
        "reason": "名称规范化后一致，可按别名覆盖并保留原产品 ID",
        "product": product,
        "candidate_numbers": product.product_no,
    }


def _ensure_alias_choice(
    meta: dict[str, Any],
    *,
    mode: str,
    alias_action: str | None,
    row_decisions: dict[int, str],
) -> None:
    """在消费暂存 token 之前拒绝「没选别名处理方式」的提交。

    预检已把冲突行写进 meta，所以这里不用重新解析上传包；返回 409 时 token
    仍然可用，用户改选后可以直接重提，不必再传一次几百兆的包。
    """
    if mode == "skip":
        # skip 的语义就是「已存在的一律不动」，别名行同样跳过，无需额外选择。
        return
    try:
        alias_rows = [int(row) for row in (meta.get("alias_rows") or [])]
    except (TypeError, ValueError):
        return
    if not alias_rows:
        return
    safe_rows = {int(row) for row in (meta.get("alias_safe_rows") or [])}
    unresolved: list[int] = []
    for row in alias_rows:
        action = row_decisions.get(row) or alias_action
        if mode == "create":
            if action != "create_new":
                unresolved.append(row)
            continue
        if action == "overwrite_alias":
            # 全局「按别名覆盖」只覆盖安全行；高风险行必须逐行确认。
            if row in safe_rows or row in row_decisions:
                continue
            unresolved.append(row)
        elif action is None:
            unresolved.append(row)
    if not unresolved:
        return
    high_risk = [row for row in unresolved if row not in safe_rows]
    if alias_action == "overwrite_alias" and high_risk:
        msg = (
            f"有 {len(high_risk)} 行别名冲突风险较高（名称不同 / 候选不唯一 / "
            "产品已删除），不能按别名自动覆盖。请逐行确认，或改选「作为新产品创建」。"
        )
    elif mode == "create":
        msg = (
            f"有 {len(unresolved)} 行产品编号存在别名冲突（只差前导 P-）。"
            "create 模式只能选择「作为新产品创建」，不会改动已有产品。"
        )
    else:
        msg = (
            f"有 {len(unresolved)} 行产品编号存在别名冲突（只差前导 P-）。"
            "请明确选择：按别名覆盖（写入原产品 ID）或作为新产品创建。"
        )
    raise HTTPException(
        status_code=409,
        detail={
            "code": 40903,
            "msg": msg,
            "alias_rows": unresolved[: settings.PRODUCT_IMPORT_CONFLICT_LIMIT],
            "alias_conflict_count": len(alias_rows),
            "alias_high_risk_rows": high_risk[: settings.PRODUCT_IMPORT_CONFLICT_LIMIT],
        },
    )


async def _product_backup_record(db: AsyncSession, product: Product) -> dict[str, Any]:
    """覆盖前的产品原值 + 图片绑定（附件 id 不变，恢复时按原顺序重建）。"""
    image_ids = (
        await db.execute(
            select(ProductImage.attachment_id)
            .where(ProductImage.product_id == product.id, ProductImage.is_deleted.is_(False))
            .order_by(ProductImage.sort, ProductImage.create_time)
        )
    ).scalars().all()
    return {
        "product_id": str(product.id),
        "product_no": product.product_no,
        "fields": {
            field: getattr(product, field)
            for field in (*_IMPORT_WRITABLE_FIELDS, "brand_id", "supplier_id", "category_id")
        },
        "image_attachment_ids": [str(value) for value in image_ids],
    }


async def _run_import(
    db: AsyncSession,
    stream,
    *,
    mode: str = "create",
    report_skipped_as_failure: bool = False,
    backup: bool = True,
    new_tag_type: str = "series",
    alias_action: str | None = None,
    alias_decisions: dict[int, str] | None = None,
) -> dict:
    """批量导入的执行体（旧 ``/import`` 与新的 ``/import/commit`` 共用）。

    ``mode`` 决定「编号已存在」怎么处理：

    * ``create``    —— 报错（旧行为）
    * ``skip``      —— 跳过，计入 ``skipped_count``，产品零变化
    * ``overwrite`` —— 原地更新：表格里有值的字段才覆盖，空单元格保留库里原值；
                       图片 / 场景图 / 标签按表格整套替换
    * ``append``    —— 只补空字段（库里为空才写），图片 / 场景图 / 标签追加

    ``alias_action`` / ``alias_decisions`` 决定「编号只差前导 P-」时怎么处理：
    未指定的别名冲突直接 409，绝不按名称自动合并；选择 ``overwrite_alias`` 时
    写的是原产品 ID（产品编号保持库里存储的原值），选择 ``create_new`` 才新增。

    覆盖 / 追加都**不改 product.id**，所以方案、报价、分享页指向的仍是同一个
    产品行；产品事实快照也不会因为改名/改价而回填到历史方案里。
    """
    if mode not in IMPORT_MODES:
        raise HTTPException(status_code=422, detail={"code": 42201, "msg": f"未知导入模式: {mode}"})
    if alias_action is not None and alias_action not in ALIAS_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail={"code": 42202, "msg": "alias_action 只能是 overwrite_alias / create_new"},
        )
    row_decisions = dict(alias_decisions or {})
    invalid_decisions = set(row_decisions.values()) - ALIAS_ACTIONS
    if invalid_decisions:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42202,
                "msg": "alias_decisions.action 只能是 overwrite_alias / create_new",
            },
        )
    if mode == "create" and alias_action == "overwrite_alias":
        raise HTTPException(
            status_code=422,
            detail={"code": 42202, "msg": "create 模式不能按别名覆盖，请改用 overwrite / append"},
        )

    # UploadFile 的底层就是个临时文件（Starlette 超过 1MB 就落盘），所以体积用 seek
    # 量、字节交给 load_bundle 按需读：一个 259MB 的包不该先在内存里躺成一份 bytes，
    # 再由 zipfile 解成第二份几百兆。
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size <= 0:
        raise HTTPException(status_code=400, detail={"code": 40003, "msg": "上传的文件是空的"})
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
            stream,
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
        tag_index = await _load_tag_index(db)

        # 编号查重一次查完，并把整行取回：覆盖 / 追加要用现有值判断「单元格空着」。
        existing: dict[str, Product] = {}
        wanted = {f.product_no for f in parsed if f.product_no}
        if wanted:
            found = await db.execute(
                select(Product).where(
                    Product.product_no.in_(wanted), Product.is_deleted.is_(False)
                )
            )
            existing = {product.product_no: product for product in found.scalars().all()}

        # 别名候选（103800022 ↔ P-103800022）：同样一次查完，含已删除行。
        alias_map = await _alias_products_by_key(
            db, {_product_no_alias_key(value) for value in wanted}
        )

        # 先把「这行能不能进库」判完，再去动图片：解析不了的行没必要为它下载/上传图片。
        failures: list[dict[str, Any]] = []
        todo: list[
            tuple[ProductRow, RowFields, dict[str, UUID], Product | None, str, str, str]
        ] = []
        seen: set[str] = set()
        seen_alias_keys: set[str] = set()
        skipped_count = 0
        unresolved_alias: list[dict[str, Any]] = []
        alias_created_count = 0
        alias_updated_count = 0
        alias_new_notes: list[str] = []
        for row, fields in zip(sheet.rows, parsed, strict=True):
            reasons = list(fields.errors)
            refs: dict[str, UUID] = {}
            current = existing.get(fields.product_no) if fields.product_no else None
            alias_info: dict[str, Any] | None = None
            alias_key = _product_no_alias_key(fields.product_no)
            if current is None and fields.product_no and not reasons:
                alias_info = _classify_alias(fields, alias_map.get(alias_key, []))
            action = ""
            if alias_info is not None:
                action = row_decisions.get(row.excel_row, "")
                if not action and alias_action == "create_new":
                    action = "create_new"
                elif (
                    not action
                    and alias_action == "overwrite_alias"
                    and alias_info["risk"] == ALIAS_RISK_SAFE
                ):
                    action = "overwrite_alias"
            target = "update" if current is not None else "create"
            effective_mode = mode
            if action == "overwrite_alias" and alias_info is not None:
                target = "update"
                effective_mode = "overwrite"
            if not reasons:
                if fields.product_no in seen or (
                    fields.product_no and alias_key in seen_alias_keys
                ):
                    reasons.append("表里有重复的产品编号，只导入第一次出现的那行")
                elif current is not None:
                    if mode == "skip":
                        if report_skipped_as_failure:
                            reasons.append("编号已存在，已跳过")
                        else:
                            skipped_count += 1
                            seen.add(fields.product_no)
                            continue
                    elif mode == "create":
                        reasons.append("产品编号已存在")
                elif alias_info is not None:
                    if mode == "skip":
                        # skip 的语义就是「已存在的一律不动」：别名同样视为已存在。
                        skipped_count += 1
                        seen.add(fields.product_no)
                        seen_alias_keys.add(alias_key)
                        continue
                    if not action:
                        unresolved_alias.append(
                            {
                                "row": row.excel_row,
                                "product_no": fields.product_no,
                                "alias_product_no": alias_info["candidate_numbers"],
                                "risk": alias_info["risk"],
                                "reason": alias_info["reason"],
                            }
                        )
                        reasons.append("产品编号存在别名冲突，尚未选择处理方式")
                    elif action == "overwrite_alias" and (
                        alias_info["product"] is None or alias_info["product"].is_deleted
                    ):
                        # 候选不唯一 / 唯一候选已删除时没有可安全写入的原产品。
                        reasons.append(
                            f"别名冲突无法确定可覆盖的原产品：{alias_info['reason']}"
                        )
                    elif action == "overwrite_alias" and alias_info["risk"] == ALIAS_RISK_HIGH:
                        # 高风险（名称不同 / 候选不唯一 / 已删除）绝不自动覆盖；
                        # 只有逐行明确选了 overwrite_alias 才放行。
                        if row_decisions.get(row.excel_row) != "overwrite_alias":
                            reasons.append(
                                f"别名冲突风险高，未覆盖：{alias_info['reason']}"
                            )
                # 品牌/供应商/分类：新建时必须给全（库里是 NOT NULL）；更新时留空表示
                # 「保留原值」，给了名字但系统里没有才算这一行失败。
                for label, name, mapping, key in (
                    ("品牌", fields.brand_name, brand_map, "brand_id"),
                    ("供应商", fields.supplier_name, supplier_map, "supplier_id"),
                    ("分类", fields.category_name, category_map, "category_id"),
                ):
                    if not name:
                        if target == "create":
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
            if action == "overwrite_alias" and alias_info is not None:
                current = alias_info["product"]
            elif action == "create_new" and alias_info is not None:
                alias_new_notes.append(
                    f"第 {row.excel_row} 行 {fields.product_no}：按你的选择作为新产品创建，"
                    f"系统里仍保留同编号别名产品 {alias_info['candidate_numbers']}"
                )
            seen.add(fields.product_no)
            if fields.product_no:
                seen_alias_keys.add(alias_key)
            notes.extend(f"第 {fields.excel_row} 行：{note}" for note in fields.notes)
            todo.append((row, fields, refs, current, target, effective_mode, action))

        if unresolved_alias:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": 40903,
                    "msg": (
                        f"这次导入有 {len(unresolved_alias)} 行产品编号存在别名冲突"
                        "（只差前导 P-）。请明确选择：按别名覆盖（写入原产品 ID）"
                        "或作为新产品创建。"
                    ),
                    "alias_conflicts": unresolved_alias[: settings.PRODUCT_IMPORT_CONFLICT_LIMIT],
                    "alias_conflict_count": len(unresolved_alias),
                },
            )
        notes.extend(alias_new_notes)

        # 标签：命中已有标签就复用；没命中的按「单元格显式类型 > 导入参数默认类型」自动创建。
        # 老实现只记一条「已忽略」，于是新系列（如摩耳）永远进不来。
        default_tag_type = _normalize_new_tag_type(new_tag_type)
        created_tag_names: list[str] = []
        pending_tags: dict[tuple[str, str], str] = {}
        for _row, fields, _refs, _current, _target, _mode, _action in todo:
            for name, hint in fields.tag_specs:
                if _resolve_tag_id(tag_index, name, hint) is not None:
                    continue
                effective_type = hint if hint is not None else default_tag_type
                pending_tags.setdefault((name, _tag_type_key(effective_type)), name)
        if pending_tags:
            for name, type_key in pending_tags:
                db.add(Tag(tag_name=name, tag_type=type_key or None))
            await db.flush()
            created_tag_names = sorted(set(pending_tags.values()))
            tag_index = await _load_tag_index(db)
            notes.append(
                f"本次新建标签 {len(created_tag_names)} 个："
                + "、".join(created_tag_names[:20])
                + ("…" if len(created_tag_names) > 20 else "")
            )

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
                [(row, fields.product_no) for row, fields, *_rest in todo],
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
    created_count = 0
    updated_count = 0
    appended_count = 0
    image_count = 0
    scene_count = 0
    images_replaced = 0
    images_appended = 0
    backup_records: list[dict[str, Any]] = []
    for row, fields, refs, current, target, effective_mode, alias_step in todo:
        buckets = per_row.get(row.excel_row, empty)
        cover = buckets["cover"]
        gallery = ([cover] if cover is not None else []) + buckets["images"]
        scenes = buckets["scenes"]
        row_images = 0
        row_scenes = 0
        # 一行一个 SAVEPOINT：撞了约束只回滚这一行，前面已经建好的产品照常保留。
        try:
            async with db.begin_nested():
                if target == "create" or current is None:
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
                    for tag_name, type_hint in fields.tag_specs:
                        tag_id = _resolve_tag_id(tag_index, tag_name, type_hint)
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
                    row_images = len(gallery)
                    row_scenes = len(scenes)
                else:
                    product = current
                    # 覆盖前留一份原值：误点「覆盖」至少能凭 backup_id 把字段与图片
                    # 绑定恢复回去（产品 id 不变，方案/报价引用不受影响）。
                    if backup:
                        backup_records.append(await _product_backup_record(db, product))
                    _apply_product_fields(product, fields, refs, effective_mode)
                    if effective_mode == "overwrite":
                        await _replace_product_tags(db, product, fields, tag_index)
                        row_images = await _replace_product_images(
                            db, product, gallery, attachments
                        )
                        if scenes:
                            await _replace_product_scenes(db, product, scenes, scene_images)
                        row_scenes = len(scenes)
                    else:
                        await _append_product_tags(db, product, fields, tag_index)
                        row_images = await _append_product_images(
                            db, product, gallery, attachments
                        )
                        row_scenes = await _append_product_scenes(
                            db, product, scenes, scene_images
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
        if target == "create" or current is None:
            created_count += 1
        elif effective_mode == "overwrite":
            updated_count += 1
            images_replaced += row_images
        else:
            appended_count += 1
            images_appended += row_images
        if alias_step == "overwrite_alias":
            alias_updated_count += 1
        elif alias_step == "create_new":
            alias_created_count += 1
        image_count += row_images
        scene_count += row_scenes

    backup_id = None
    if backup_records:
        try:
            backup_id = await asyncio.to_thread(
                write_import_backup, backup_records, mode=mode
            )
        except OSError:
            logger.warning("批量导入：覆盖前快照写入失败", exc_info=True)
            notes.append("覆盖前的产品快照没能写入，本次覆盖不可回滚，请核对结果")

    await db.commit()
    failures.sort(key=lambda item: item["row"])

    return {
        "code": 200,
        "data": {
            "total": len(sheet.rows),
            "success_count": success,
            "fail_count": len(failures),
            "failures": failures,
            "created_count": created_count,
            "updated_count": updated_count,
            "appended_count": appended_count,
            "skipped_count": skipped_count,
            "alias_updated_count": alias_updated_count,
            "alias_created_count": alias_created_count,
            "images_replaced": images_replaced,
            "images_appended": images_appended,
            "created_tags": len(created_tag_names),
            "new_tag_names": _capped(created_tag_names),
            "mode": mode,
            "backup_id": backup_id,
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


class ImportAliasDecision(BaseModel):
    """对单行别名冲突的明确决定（行号即表格里的 excel_row）。"""

    row: int
    action: str


class ImportCommitRequest(BaseModel):
    """预检通过后的提交参数。"""

    token: str
    mode: str = "overwrite"
    backup: bool = True
    # 表格里没写类型的「新标签」归到哪一类：series（默认）或 none。
    # 单元格里写了「系列:摩耳」这类显式类型的，以单元格为准。
    new_tag_type: str = "series"
    # 别名冲突（103800022 ↔ P-103800022）的处理方式：不选就拒绝提交。
    alias_action: str | None = None
    alias_decisions: list[ImportAliasDecision] = []


@router.post("/import", dependencies=[Depends(PermissionChecker("product:import"))])
@audit_action("product_import", module="products")
async def import_products(
    request: Request,
    file: UploadFile = File(...),
    skip_if_exists: bool = Query(False, alias="skipIfExists"),
    db: AsyncSession = Depends(get_db),
):
    """批量导入产品（旧入口，保留兼容）。

    勾 skipIfExists 等价于新的 skip 模式；否则是 create 模式（编号已存在即失败）。
    新前端走 ``/import/preflight`` -> ``/import/commit``，能先看清冲突再决定
    覆盖 / 追加 / 跳过。
    """
    return await _run_import(
        db,
        file.file,
        mode="skip" if skip_if_exists else "create",
        # 旧前端把「已跳过」显示在失败明细里，保留这条兼容行为
        report_skipped_as_failure=skip_if_exists,
    )


@router.post(
    "/import/preflight", dependencies=[Depends(PermissionChecker("product:import"))]
)
@audit_action("product_import_preflight", module="products")
async def preflight_import(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """只解析、只查重，不写库：先让用户看清这次重传会发生什么。

    图片阶段一律不做（不下载、不解析字节）：预检只需要知道「这行有几张图」，
    为了数个数把一个 259MB 的包里的图片全部取一遍并不划算。真正的出图与上传
    留到 commit。
    """
    user_id = str(getattr(request.state, "user_id", "") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail={"code": 40101, "msg": "请先登录"})

    # 预检是唯一会持续产生暂存目录的入口，用它顺带做一次限频清理（每小时最多一次），
    # 免得为了 TTL 再单独引一个 cron；容器重启后也能自愈。
    _maybe_cleanup_staging()

    try:
        meta = stage_upload(
            file.file,
            file_name=file.filename or "products.xlsx",
            user_id=user_id,
            max_bytes=settings.PRODUCT_IMPORT_MAX_FILE_BYTES,
        )
    except StagingError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "msg": exc.message}
        ) from exc

    token = meta["token"]
    try:
        upload_path, meta = load_staged(token, user_id=user_id)
        with upload_path.open("rb") as stream:
            bundle = load_bundle(
                stream,
                max_image_bytes=settings.PRODUCT_IMPORT_MAX_IMAGE_BYTES,
                max_total_bytes=settings.PRODUCT_IMPORT_MAX_FILE_BYTES,
            )
            try:
                sheet = read_product_sheet(bundle.xlsx)
                bundle_warnings = list(bundle.warnings)
            finally:
                bundle.close()
    except StagingError as exc:
        discard_staged(token, user_id=user_id)
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "msg": exc.message}
        ) from exc
    except MediaError as exc:
        discard_staged(token, user_id=user_id)
        raise HTTPException(status_code=400, detail={"code": 40003, "msg": str(exc)}) from exc
    except SheetError as exc:
        discard_staged(token, user_id=user_id)
        raise HTTPException(status_code=400, detail={"code": 40001, "msg": str(exc)}) from exc
    except Exception:
        discard_staged(token, user_id=user_id)
        raise

    if len(sheet.rows) > settings.PRODUCT_IMPORT_MAX_ROWS:
        discard_staged(token, user_id=user_id)
        raise HTTPException(
            status_code=400,
            detail={
                "code": 40004,
                "msg": f"表里有 {len(sheet.rows)} 行数据，超过单次上限 "
                f"{settings.PRODUCT_IMPORT_MAX_ROWS} 行，请拆分后导入",
            },
        )

    notes: list[str] = list(sheet.warnings)
    if sheet.unknown_headers:
        notes.append("这些列没认出来，已忽略：" + "、".join(sheet.unknown_headers))

    parsed = [parse_row(row) for row in sheet.rows]
    brand_map = await _name_to_id(
        db, Brand, Brand.brand_name, {f.brand_name for f in parsed if f.brand_name}
    )
    supplier_map = await _name_to_id(
        db, Supplier, Supplier.supplier_name, {f.supplier_name for f in parsed if f.supplier_name}
    )
    category_map = await _name_to_id(
        db, Category, Category.category_name, {f.category_name for f in parsed if f.category_name}
    )

    existing: dict[str, tuple[UUID, str, int]] = {}
    wanted = {f.product_no for f in parsed if f.product_no}
    # 别名候选一次查完（含已软删除：删掉的产品同样不能被自动覆盖）。
    alias_map = await _alias_products_by_key(
        db, {_product_no_alias_key(value) for value in wanted}
    )
    exact_rows = []
    if wanted:
        exact_rows = (
            await db.execute(
                select(Product.id, Product.product_no, Product.product_name).where(
                    Product.product_no.in_(wanted), Product.is_deleted.is_(False)
                )
            )
        ).all()
    image_counts: dict[UUID, int] = {}
    product_ids = [row.id for row in exact_rows]
    product_ids.extend(p.id for products in alias_map.values() for p in products)
    if product_ids:
        count_rows = (
            await db.execute(
                select(ProductImage.product_id, func.count())
                .where(
                    ProductImage.product_id.in_(product_ids),
                    ProductImage.is_deleted.is_(False),
                )
                .group_by(ProductImage.product_id)
            )
        ).all()
        image_counts = {product_id: count for product_id, count in count_rows}
    for row in exact_rows:
        existing[row.product_no] = (row.id, row.product_name, image_counts.get(row.id, 0))

    conflicts: list[dict[str, Any]] = []
    alias_conflicts: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_alias_keys: set[str] = set()
    new_count = 0
    existing_count = 0
    invalid_count = 0
    alias_safe_count = 0
    alias_high_risk_count = 0
    for row, fields in zip(sheet.rows, parsed, strict=True):
        reasons = list(fields.errors)
        is_existing = fields.product_no in existing
        alias_key = _product_no_alias_key(fields.product_no)
        alias_info = None
        if not is_existing and fields.product_no and not reasons:
            alias_info = _classify_alias(fields, alias_map.get(alias_key, []))
        # 别名命中的产品已经在库里：允许靠原值补全主数据，和精确命中同样对待。
        is_known = is_existing or alias_info is not None
        if not reasons:
            if fields.product_no in seen or (
                fields.product_no and alias_key in seen_alias_keys
            ):
                reasons.append("表里有重复的产品编号，只导入第一次出现的那行")
            else:
                for label, name, mapping in (
                    ("品牌", fields.brand_name, brand_map),
                    ("供应商", fields.supplier_name, supplier_map),
                    ("分类", fields.category_name, category_map),
                ):
                    if not name:
                        # 已有产品可以靠原值补全，新建产品必须自己给全
                        if not is_known:
                            reasons.append(f"{label}为空（产品必须挂在{label}下）")
                        continue
                    if name not in mapping:
                        reasons.append(f"{label}「{name}」系统里没有，请先建好再导入")
        if reasons:
            invalid_count += 1
            invalid.append(
                {
                    "row": row.excel_row,
                    "product_no": fields.product_no,
                    "reason": "；".join(reasons),
                }
            )
            continue
        seen.add(fields.product_no)
        if fields.product_no:
            seen_alias_keys.add(alias_key)
        if is_existing:
            existing_count += 1
            _, existing_name, image_count = existing[fields.product_no]
            conflicts.append(
                {
                    "row": row.excel_row,
                    "product_no": fields.product_no,
                    "product_name": fields.product_name,
                    "existing_name": existing_name,
                    "existing_image_count": image_count,
                }
            )
        elif alias_info is not None:
            alias_product = alias_info["product"]
            if alias_info["risk"] == ALIAS_RISK_SAFE:
                alias_safe_count += 1
            else:
                alias_high_risk_count += 1
            alias_conflicts.append(
                {
                    "row": row.excel_row,
                    "product_no": fields.product_no,
                    "product_name": fields.product_name,
                    "alias_product_id": (
                        str(alias_product.id) if alias_product is not None else None
                    ),
                    "alias_product_no": alias_info["candidate_numbers"],
                    "existing_name": (
                        alias_product.product_name if alias_product is not None else None
                    ),
                    "existing_image_count": (
                        image_counts.get(alias_product.id, 0)
                        if alias_product is not None
                        else 0
                    ),
                    "risk": alias_info["risk"],
                    "reason": alias_info["reason"],
                }
            )
        else:
            new_count += 1

    limit = settings.PRODUCT_IMPORT_CONFLICT_LIMIT

    # 把别名冲突行写进暂存元数据：commit 在消费 token 之前就能拒绝「未选择
    # 别名处理方式」的提交，用户还能用同一个 token 重新选择，不必重传大包。
    try:
        update_staged_meta(
            token,
            user_id=user_id,
            alias_conflict_count=len(alias_conflicts),
            alias_rows=[item["row"] for item in alias_conflicts],
            alias_safe_rows=[
                item["row"] for item in alias_conflicts if item["risk"] == ALIAS_RISK_SAFE
            ],
            alias_high_risk_rows=[
                item["row"] for item in alias_conflicts if item["risk"] == ALIAS_RISK_HIGH
            ],
        )
    except StagingError:
        logger.warning("导入预检：别名冲突元数据写入失败", exc_info=True)

    # 预检里把「会被新建的标签」也列出来：用户在弹窗就能看到「摩耳」将被创建，
    # 并选择新标签归入「系列」（默认）还是「未分组」。这里不写库。
    tag_index = await _load_tag_index(db)
    new_tags: list[dict[str, Any]] = []
    seen_new_tags: set[tuple[str, str]] = set()
    for _row, fields in zip(sheet.rows, parsed, strict=True):
        if fields.errors:
            continue
        for name, hint in fields.tag_specs:
            if _resolve_tag_id(tag_index, name, hint) is not None:
                continue
            effective = hint if hint is not None else "series"
            key = (name, _tag_type_key(effective))
            if key in seen_new_tags:
                continue
            seen_new_tags.add(key)
            new_tags.append({"name": name, "tag_type": effective})

    return {
        "code": 200,
        "data": {
            "token": token,
            "expires_at": datetime.datetime.fromtimestamp(
                float(meta["expires_at"]), datetime.UTC
            ).isoformat(),
            "file_name": meta["file_name"],
            "size": meta["size"],
            "sha256": meta["sha256"],
            "header_row": sheet.header_row,
            "total_rows": len(sheet.rows),
            "new_count": new_count,
            "existing_count": existing_count,
            "exact_existing_count": existing_count,
            "alias_conflict_count": len(alias_conflicts),
            "alias_safe_count": alias_safe_count,
            "alias_high_risk_count": alias_high_risk_count,
            "invalid_count": invalid_count,
            "new_tags": new_tags[:limit],
            "new_tag_count": len(new_tags),
            "new_tag_type_default": "series",
            "conflicts": conflicts[:limit],
            "conflicts_truncated": len(conflicts) > limit,
            "alias_conflicts": alias_conflicts[:limit],
            "alias_conflicts_truncated": len(alias_conflicts) > limit,
            "invalid": invalid[:limit],
            "invalid_truncated": len(invalid) > limit,
            "notes": _capped(notes),
            "image_warnings": _capped(bundle_warnings),
            "unknown_headers": sheet.unknown_headers,
        },
    }


@router.post("/import/commit", dependencies=[Depends(PermissionChecker("product:import"))])
@audit_action("product_import_commit", module="products")
async def commit_import(
    request: Request,
    payload: ImportCommitRequest,
    db: AsyncSession = Depends(get_db),
):
    """按用户选择的模式真正写库（覆盖 / 追加 / 跳过）。"""
    user_id = str(getattr(request.state, "user_id", "") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail={"code": 40101, "msg": "请先登录"})

    mode = (payload.mode or "").strip().lower()
    if mode not in {"overwrite", "append", "skip"}:
        raise HTTPException(
            status_code=422,
            detail={"code": 42201, "msg": "mode 只能是 overwrite / append / skip"},
        )

    alias_action = (payload.alias_action or "").strip().lower() or None
    if alias_action is not None and alias_action not in ALIAS_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail={"code": 42202, "msg": "alias_action 只能是 overwrite_alias / create_new"},
        )
    if mode == "create" and alias_action == "overwrite_alias":
        raise HTTPException(
            status_code=422,
            detail={"code": 42202, "msg": "create 模式不能按别名覆盖，请改用 overwrite / append"},
        )
    row_decisions: dict[int, str] = {}
    for decision in payload.alias_decisions:
        if decision.action not in ALIAS_ACTIONS:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": 42202,
                    "msg": "alias_decisions.action 只能是 overwrite_alias / create_new",
                },
            )
        row_decisions[decision.row] = decision.action

    # 先只读暂存元数据：别名没选就 409，且不消费 token，用户改选后可原样重提。
    try:
        _upload_path, meta = load_staged(payload.token, user_id=user_id)
    except StagingError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "msg": exc.message}
        ) from exc
    _ensure_alias_choice(
        meta, mode=mode, alias_action=alias_action, row_decisions=row_decisions
    )

    try:
        upload_path, _meta = consume_staged(payload.token, user_id=user_id)
    except StagingError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "msg": exc.message}
        ) from exc

    with upload_path.open("rb") as stream:
        return await _run_import(
            db,
            stream,
            mode=mode,
            backup=payload.backup,
            new_tag_type=payload.new_tag_type,
            alias_action=alias_action,
            alias_decisions=row_decisions,
        )


@router.delete(
    "/import/preflight/{token}",
    dependencies=[Depends(PermissionChecker("product:import"))],
)
async def cancel_import_preflight(request: Request, token: str):
    """取消预检：立刻删掉暂存文件，释放磁盘。"""
    user_id = str(getattr(request.state, "user_id", "") or "")
    discard_staged(token, user_id=user_id)
    return {"code": 200, "msg": "success"}
