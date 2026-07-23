import datetime
import io
from collections.abc import Iterator
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.minio_client import get_minio_client
from app.core.permission import PermissionChecker
from app.core.security import create_access_token, decode_access_token
from app.middleware.audit import audit_action
from app.models.product import Attachment, Product, ProductImage, ProductManual, SceneImage, product_scene_image
from app.schemas.file import FilePresignResponse, FileReferences, FileUploadResponse

router = APIRouter()

ALLOWED_FILE_TYPES = frozenset({"image", "video", "pdf", "doc", "other"})

_ALLOWED = {
    "image/jpeg": ("image", 50 * 1024 * 1024),
    "image/png": ("image", 50 * 1024 * 1024),
    "image/webp": ("image", 50 * 1024 * 1024),
    "video/mp4": ("video", 100 * 1024 * 1024),
    "application/pdf": ("pdf", 50 * 1024 * 1024),
    "application/msword": ("doc", 50 * 1024 * 1024),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        "doc",
        50 * 1024 * 1024,
    ),
}

_PREVIEW_EXPIRE_SECONDS = 900
_DOWNLOAD_EXPIRE_MINUTES = 5
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


def _content_type_for(attachment: Attachment) -> str:
    if attachment.file_type == "pdf":
        return "application/pdf"
    if attachment.file_type == "image":
        suffix = attachment.oss_key.rsplit(".", 1)[-1].lower()
        if suffix in {"jpg", "jpeg"}:
            return "image/jpeg"
        if suffix == "png":
            return "image/png"
        if suffix == "webp":
            return "image/webp"
    return "application/octet-stream"


def _iter_minio_object(obj) -> Iterator[bytes]:
    try:
        for chunk in obj.stream(1024 * 1024):
            yield chunk
    finally:
        obj.close()
        obj.release_conn()


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("media:view"))])
async def list_files(
    request: Request,
    keyword: str | None = None,
    file_type: str | None = None,
    referenced: bool | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Attachment)
        .where(Attachment.is_deleted.is_(False))
    )
    if keyword:
        query = query.where(Attachment.file_name.ilike(f"%{keyword}%"))
    if file_type:
        if file_type not in ALLOWED_FILE_TYPES:
            raise HTTPException(
                status_code=422,
                detail={"code": 42201, "msg": f"不支持的文件类型筛选: {file_type}"},
            )
        query = query.where(Attachment.file_type == file_type)

    if referenced is not None:
        has_product_image = (
            select(1)
            .where(ProductImage.attachment_id == Attachment.id, ProductImage.is_deleted.is_(False))
            .exists()
        )
        has_manual = (
            select(1)
            .where(ProductManual.attachment_id == Attachment.id, ProductManual.is_deleted.is_(False))
            .exists()
        )
        has_scene = (
            select(1)
            .where(SceneImage.attachment_id == Attachment.id, SceneImage.is_deleted.is_(False))
            .exists()
        )
        if referenced:
            query = query.where(or_(has_product_image, has_manual, has_scene))
        else:
            query = query.where(~or_(has_product_image, has_manual, has_scene))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    query = query.order_by(Attachment.create_time.desc())
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    attachments = result.scalars().all()

    items = []
    for att in attachments:
        ref_count = await _count_refs(db, att.id)
        preview_url = _create_content_url(request, att.id)
        items.append({
            "id": str(att.id),
            "file_name": att.file_name,
            "file_url": att.file_url,
            "preview_url": preview_url,
            "file_type": att.file_type,
            "file_size": att.file_size,
            "storage_type": att.storage_type,
            "oss_key": att.oss_key,
            "create_time": att.create_time.isoformat() if att.create_time else None,
            "update_time": att.update_time.isoformat() if att.update_time else None,
            "ref_count": ref_count,
        })

    return {
        "code": 200,
        "data": {
            "list": items,
            "total": total,
            "page": page,
            "size": size,
        },
    }


async def _count_refs(db: AsyncSession, attachment_id: UUID) -> int:
    total = 0
    for ref_cls, fk_col in [
        (ProductImage, ProductImage.attachment_id),
        (ProductManual, ProductManual.attachment_id),
        (SceneImage, SceneImage.attachment_id),
    ]:
        result = await db.execute(
            select(func.count())
            .select_from(ref_cls)
            .where(fk_col == attachment_id, ref_cls.is_deleted.is_(False))
        )
        total += result.scalar() or 0
    return total


async def _check_refs(db: AsyncSession, attachment_id: UUID) -> list[str]:
    refs = []
    img_result = await db.execute(
        select(func.count())
        .select_from(ProductImage)
        .where(ProductImage.attachment_id == attachment_id, ProductImage.is_deleted.is_(False))
    )
    if img_result.scalar() > 0:
        refs.append("产品图片")

    manual_result = await db.execute(
        select(func.count())
        .select_from(ProductManual)
        .where(ProductManual.attachment_id == attachment_id, ProductManual.is_deleted.is_(False))
    )
    if manual_result.scalar() > 0:
        refs.append("产品说明书")

    scene_result = await db.execute(
        select(func.count())
        .select_from(SceneImage)
        .where(SceneImage.attachment_id == attachment_id, SceneImage.is_deleted.is_(False))
    )
    if scene_result.scalar() > 0:
        refs.append("场景图")

    return refs


async def _fetch_references(db: AsyncSession, attachment_id: UUID) -> FileReferences:
    refs = FileReferences()

    # Product images
    pi_result = await db.execute(
        select(ProductImage, Product)
        .join(Product, Product.id == ProductImage.product_id)
        .where(
            ProductImage.attachment_id == attachment_id,
            ProductImage.is_deleted.is_(False),
            Product.is_deleted.is_(False),
        )
    )
    for pi, p in pi_result.fetchall():
        refs.product_images.append({
            "product_id": str(p.id),
            "product_no": p.product_no,
            "product_name": p.product_name,
            "product_image_id": str(pi.id),
            "is_cover": pi.is_cover,
        })

    # Scene images
    si_result = await db.execute(
        select(SceneImage)
        .where(
            SceneImage.attachment_id == attachment_id,
            SceneImage.is_deleted.is_(False),
        )
    )
    scene_images = si_result.scalars().all()
    for si in scene_images:
        bound_products = []
        binding_result = await db.execute(
            select(product_scene_image.c.product_id)
            .join(Product, Product.id == product_scene_image.c.product_id)
            .where(
                product_scene_image.c.scene_image_id == si.id,
                product_scene_image.c.is_deleted.is_(False),
                Product.is_deleted.is_(False),
            )
        )
        for row in binding_result.fetchall():
            product = await db.execute(
                select(Product).where(Product.id == row.product_id, Product.is_deleted.is_(False))
            )
            p = product.scalar_one_or_none()
            if p:
                bound_products.append({
                    "product_id": str(p.id),
                    "product_no": p.product_no,
                    "product_name": p.product_name,
                })
        refs.scene_images.append({
            "scene_image_id": str(si.id),
            "scene_image_name": si.name,
            "bound_products": bound_products,
        })

    # Manuals
    pm_result = await db.execute(
        select(ProductManual, Product)
        .join(Product, Product.id == ProductManual.product_id)
        .where(
            ProductManual.attachment_id == attachment_id,
            ProductManual.is_deleted.is_(False),
            Product.is_deleted.is_(False),
        )
    )
    for pm, p in pm_result.fetchall():
        refs.manuals.append({
            "manual_id": str(pm.id),
            "product_id": str(p.id),
            "product_no": p.product_no,
            "product_name": p.product_name,
            "doc_type": pm.doc_type,
        })

    return refs


@router.get(
    "/{attachment_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("media:view"))],
)
async def get_file(
    request: Request,
    attachment_id: UUID,
    with_references: bool = Query(False, description="是否同时返回引用详情"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Attachment).where(
            Attachment.id == attachment_id, Attachment.is_deleted.is_(False)
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})

    ref_count = await _count_refs(db, attachment_id)
    references = None
    if with_references:
        references = await _fetch_references(db, attachment_id)

    preview_url = _create_content_url(request, attachment.id)

    body = {
        "id": str(attachment.id),
        "file_name": attachment.file_name,
        "file_type": attachment.file_type,
        "file_size": attachment.file_size,
        "file_url": attachment.file_url,
        "preview_url": preview_url,
        "create_time": attachment.create_time.isoformat() if attachment.create_time else None,
        "update_time": attachment.update_time.isoformat() if attachment.update_time else None,
        "ref_count": ref_count,
    }
    if references is not None:
        body["references"] = references.model_dump(mode="json")

    return {"code": 200, "data": body}


@router.get(
    "/{attachment_id}/references",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("media:view"))],
)
async def get_file_references(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Attachment).where(
            Attachment.id == attachment_id, Attachment.is_deleted.is_(False)
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})

    references = await _fetch_references(db, attachment_id)
    ref_count = await _count_refs(db, attachment_id)

    return {
        "code": 200,
        "data": {
            "ref_count": ref_count,
            "references": references.model_dump(mode="json"),
        },
    }


@router.post(
    "/upload",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("media:upload"))],
)
@audit_action("file_upload", module="files", target_id_kwarg="attachment_id")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content_type = file.content_type or ""
    if content_type not in _ALLOWED:
        raise HTTPException(
            status_code=422,
            detail={"code": 42202, "msg": f"不支持的文件类型: {content_type}"},
        )
    file_type, max_size = _ALLOWED[content_type]

    data = await file.read()
    if len(data) > max_size:
        raise HTTPException(
            status_code=422,
            detail={"code": 42203, "msg": f"文件大小超过上限 {max_size} 字节"},
        )

    extension = content_type.split("/")[-1]
    if content_type == "application/pdf":
        extension = "pdf"
    object_key = f"{file_type}/{uuid4().hex}.{extension}"
    client = get_minio_client()
    try:
        client.make_bucket(settings.MINIO_BUCKET)
    except Exception:
        pass
    client.put_object(
        settings.MINIO_BUCKET,
        object_key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )

    attachment = Attachment(
        file_name=file.filename or object_key,
        file_url=f"/files/{object_key}",
        file_type=file_type,
        file_size=len(data),
        storage_type="minio",
        oss_key=object_key,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    try:
        preview_url = _create_content_url(request, attachment.id)
    except Exception:
        preview_url = None

    return {
        "code": 200,
        "data": FileUploadResponse(
            attachment_id=attachment.id,
            file_name=attachment.file_name,
            file_url=attachment.file_url,
            preview_url=preview_url,
            file_type=attachment.file_type,
            file_size=attachment.file_size,
        ).model_dump(),
    }


@router.put(
    "/{attachment_id}/replace",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("media:replace"))],
)
@audit_action("file_replace", module="files", target_id_kwarg="attachment_id")
async def replace_file(
    request: Request,
    attachment_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted.is_(False))
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})

    content_type = file.content_type or ""
    if content_type not in _ALLOWED:
        raise HTTPException(
            status_code=422,
            detail={"code": 42202, "msg": f"不支持的文件类型: {content_type}"},
        )
    file_type, max_size = _ALLOWED[content_type]

    if file_type != attachment.file_type:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42204,
                "msg": f"替换文件类型不匹配：原文件类型为 {attachment.file_type}，新文件类型为 {file_type}",
            },
        )

    data = await file.read()
    if len(data) > max_size:
        raise HTTPException(
            status_code=422,
            detail={"code": 42203, "msg": f"文件大小超过上限 {max_size} 字节"},
        )

    extension = content_type.split("/")[-1]
    if content_type == "application/pdf":
        extension = "pdf"
    object_key = f"{file_type}/{uuid4().hex}.{extension}"
    client = get_minio_client()
    try:
        client.make_bucket(settings.MINIO_BUCKET)
    except Exception:
        pass
    client.put_object(
        settings.MINIO_BUCKET,
        object_key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )

    old_oss_key = attachment.oss_key
    attachment.file_name = file.filename or object_key
    attachment.file_url = f"/files/{object_key}"
    attachment.file_size = len(data)
    attachment.oss_key = object_key

    await db.commit()
    await db.refresh(attachment)

    # 清理旧对象存储文件
    # 如果项目策略不允许物理删除，可注释掉以下行。
    # 当前策略：替换后旧文件不再需要，从 MinIO 中移除。
    try:
        client.remove_object(settings.MINIO_BUCKET, old_oss_key)
    except Exception:
        pass

    try:
        preview_url = _create_content_url(request, attachment.id)
    except Exception:
        preview_url = None

    return {
        "code": 200,
        "data": FileUploadResponse(
            attachment_id=attachment.id,
            file_name=attachment.file_name,
            file_url=attachment.file_url,
            preview_url=preview_url,
            file_type=attachment.file_type,
            file_size=attachment.file_size,
        ).model_dump(),
    }


@router.delete(
    "/{attachment_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("media:delete"))],
)
@audit_action("file_delete", module="files", target_id_kwarg="attachment_id")
async def delete_file(request: Request, attachment_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted.is_(False))
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})

    refs = await _check_refs(db, attachment_id)
    if refs:
        references = await _fetch_references(db, attachment_id)
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": f"附件被 {', '.join(refs)} 引用，请先解除关联",
                "references": references.model_dump(mode="json"),
            },
        )

    attachment.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}


@router.get("/{attachment_id}/content")
async def get_file_content(
    attachment_id: UUID,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_access_token(token)
    if (
        not payload
        or payload.get("scope") != _CONTENT_TOKEN_SCOPE
        or payload.get("attachment_id") != str(attachment_id)
    ):
        raise HTTPException(status_code=401, detail={"code": 40102, "msg": "文件访问链接已失效"})

    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted.is_(False))
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})

    client = get_minio_client()
    try:
        obj = client.get_object(settings.MINIO_BUCKET, attachment.oss_key)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": 40402, "msg": "文件对象不存在或无法读取"},
        ) from exc

    content_disposition = "inline"
    filename = quote(attachment.file_name)
    headers = {
        "Content-Disposition": f"{content_disposition}; filename*=UTF-8''{filename}",
        "Cache-Control": f"private, max-age={_PREVIEW_EXPIRE_SECONDS}",
    }
    return StreamingResponse(
        _iter_minio_object(obj),
        media_type=_content_type_for(attachment),
        headers=headers,
    )


@router.get(
    "/{attachment_id}/download",
    dependencies=[Depends(PermissionChecker("media:view"))],
)
@audit_action("file_download", module="files", target_id_kwarg="attachment_id")
async def download_file(
    request: Request,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted.is_(False))
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})

    client = get_minio_client()
    url = client.presigned_get_object(
        settings.MINIO_BUCKET,
        attachment.oss_key,
        expires=datetime.timedelta(minutes=_DOWNLOAD_EXPIRE_MINUTES),
    )
    return RedirectResponse(url=url, status_code=307)


@router.get(
    "/{attachment_id}/preview",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("media:view"))],
)
@audit_action("file_preview", module="files", target_id_kwarg="attachment_id")
async def preview_file(
    request: Request,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted.is_(False))
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})

    url = _create_content_url(request, attachment.id)
    return {
        "code": 200,
        "data": FilePresignResponse(
            preview_url=url, expire_in=_PREVIEW_EXPIRE_SECONDS
        ).model_dump(),
    }
