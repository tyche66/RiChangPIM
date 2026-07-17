import datetime
import io
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.minio_client import get_minio_client
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.product import Attachment, ProductImage, ProductManual
from app.schemas.file import FilePresignResponse, FileUploadResponse

router = APIRouter()

# ---------------------------------------------------------------------------
# 附件 file_type 的 canonical 取值。
#
# 依据：0001_initial.py 的 CHECK 约束 `check_attachment_file_type` 仅允许
#   image / video / pdf / doc / other
# 未发现任何已交付规范（docs / schema / 测试）要求使用 "document"。因此以数据库
# 约束为准：PDF -> "pdf"，Word(.doc/.docx) -> "doc"。这样上传写入的 file_type 一定
# 满足 CHECK 约束，避免 IntegrityError（原实现写入 "document" 会直接违反约束）。
# ---------------------------------------------------------------------------
# 与 0001_initial.py CHECK 约束保持一致的允许集合（供自身校验与测试断言使用）。
ALLOWED_FILE_TYPES = frozenset({"image", "video", "pdf", "doc", "other"})

# docs/04 第十四章：完整扩展名 / MIME 白名单 + 大小上限
# value = (file_type, max_size_bytes)；file_type 必须 ∈ ALLOWED_FILE_TYPES。
_ALLOWED = {
    "image/jpeg": ("image", 10 * 1024 * 1024),
    "image/png": ("image", 10 * 1024 * 1024),
    "image/webp": ("image", 10 * 1024 * 1024),
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


@router.post(
    "/upload",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("file:upload"))],
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

    object_key = f"{file_type}/{uuid4().hex}_{file.filename}"
    client = get_minio_client()
    try:
        client.make_bucket(settings.MINIO_BUCKET)
    except Exception:  # noqa: BLE001 - 桶已存在等情况忽略
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

    return {
        "code": 200,
        "data": FileUploadResponse(
            attachment_id=attachment.id,
            file_name=attachment.file_name,
            file_url=attachment.file_url,
            file_type=attachment.file_type,
            file_size=attachment.file_size,
        ).model_dump(),
    }


@router.delete(
    "/{attachment_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("file:delete"))],
)
@audit_action("file_delete", module="files", target_id_kwarg="attachment_id")
async def delete_file(request: Request, attachment_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted.is_(False))
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})

    img_refs = await db.execute(
        select(func.count())
        .select_from(ProductImage)
        .where(ProductImage.attachment_id == attachment_id, ProductImage.is_deleted.is_(False))
    )
    manual_refs = await db.execute(
        select(func.count())
        .select_from(ProductManual)
        .where(ProductManual.attachment_id == attachment_id, ProductManual.is_deleted.is_(False))
    )
    if img_refs.scalar_one() > 0 or manual_refs.scalar_one() > 0:
        raise HTTPException(
            status_code=422,
            detail={"code": 42201, "msg": "附件被产品图片/说明书引用，请先解除关联"},
        )

    attachment.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}


@router.get(
    "/{attachment_id}/download",
    dependencies=[Depends(PermissionChecker("file:view"))],
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
    dependencies=[Depends(PermissionChecker("file:view"))],
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

    client = get_minio_client()
    url = client.presigned_get_object(
        settings.MINIO_BUCKET,
        attachment.oss_key,
        expires=datetime.timedelta(seconds=_PREVIEW_EXPIRE_SECONDS),
    )
    return {
        "code": 200,
        "data": FilePresignResponse(
            preview_url=url, expire_in=_PREVIEW_EXPIRE_SECONDS
        ).model_dump(),
    }
