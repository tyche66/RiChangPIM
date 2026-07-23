import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.security import create_access_token
from app.middleware.audit import audit_action
from app.models.product import Attachment, Product, SceneImage, product_scene_image

router = APIRouter()

MAX_PRODUCT_SCENE_IMAGES = 30
_PREVIEW_EXPIRE_SECONDS = 900
_CONTENT_TOKEN_SCOPE = "file_content"


class SceneImageCreate(BaseModel):
    name: str
    attachment_id: UUID
    sort: int = 0
    product_ids: list[UUID] = []


class SceneImageUpdate(BaseModel):
    name: str | None = None
    attachment_id: UUID | None = None
    sort: int | None = None


class SceneImageBind(BaseModel):
    product_ids: list[UUID]


class SceneImageUnbind(BaseModel):
    product_ids: list[UUID]


class SceneImageBatchBind(BaseModel):
    scene_image_ids: list[UUID]
    product_ids: list[UUID]


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


def _scene_image_response(si: SceneImage, request: Request) -> dict:
    preview_url = _create_content_url(request, si.attachment.id) if si.attachment else None
    return {
        "id": str(si.id),
        "name": si.name,
        "attachment_id": str(si.attachment_id),
        "file_url": si.attachment.file_url if si.attachment else None,
        "preview_url": preview_url,
        "file_name": si.attachment.file_name if si.attachment else None,
        "file_type": si.attachment.file_type if si.attachment else None,
        "sort": si.sort,
        "create_time": si.create_time.isoformat() if si.create_time else None,
        "update_time": si.update_time.isoformat() if si.update_time else None,
        "bound_products": [
            {
                "id": str(p.id),
                "product_no": p.product_no,
                "product_name": p.product_name,
            }
            for p in si.products
        ],
    }


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("scene_image:view"))])
async def list_scene_images(
    request: Request,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(SceneImage)
        .options(
            joinedload(SceneImage.attachment),
            selectinload(SceneImage.products),
        )
        .where(SceneImage.is_deleted.is_(False))
    )
    if keyword:
        query = query.where(SceneImage.name.ilike(f"%{keyword}%"))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    query = query.order_by(SceneImage.sort, SceneImage.create_time.desc())
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    scene_images = result.scalars().all()

    return {
        "code": 200,
        "data": {
            "list": [_scene_image_response(si, request) for si in scene_images],
            "total": total,
            "page": page,
            "size": size,
        },
    }


@router.post(
    "",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("scene_image:create"))],
)
@audit_action("scene_image_create", module="scene_images", target_id_kwarg="id")
async def create_scene_image(
    request: Request,
    data: SceneImageCreate,
    db: AsyncSession = Depends(get_db),
):
    attachment = await db.scalar(
        select(Attachment).where(
            Attachment.id == data.attachment_id, Attachment.is_deleted.is_(False)
        )
    )
    if not attachment:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})
    if attachment.file_type != "image":
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "仅允许 image 类型的附件"}
        )

    scene_image = SceneImage(
        name=data.name,
        attachment_id=data.attachment_id,
        sort=data.sort,
    )
    db.add(scene_image)
    await db.flush()

    if data.product_ids:
        products = await db.scalars(
            select(Product)
            .where(Product.id.in_(data.product_ids), Product.is_deleted.is_(False))
        )
        product_map = {str(p.id): p for p in products.all()}
        for pid in data.product_ids:
            pid_str = str(pid)
            if pid_str not in product_map:
                continue

            current_count_result = await db.execute(
                select(func.count()).select_from(product_scene_image).where(
                    product_scene_image.c.product_id == product_map[pid_str].id,
                    product_scene_image.c.is_deleted.is_(False),
                )
            )
            current_count = current_count_result.scalar() or 0
            if current_count >= MAX_PRODUCT_SCENE_IMAGES:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": 42201,
                        "msg": (
                            f"产品 {product_map[pid_str].product_no} "
                            f"场景图数量已达上限（最多 {MAX_PRODUCT_SCENE_IMAGES} 张）"
                        ),
                    },
                )

            # 检查是否有软删除的旧记录，有则恢复
            existing_deleted = await db.execute(
                select(product_scene_image).where(
                    product_scene_image.c.product_id == product_map[pid_str].id,
                    product_scene_image.c.scene_image_id == scene_image.id,
                    product_scene_image.c.is_deleted.is_(True),
                )
            )
            if existing_deleted.scalar_one_or_none():
                await db.execute(
                    product_scene_image.update()
                    .where(
                        product_scene_image.c.product_id == product_map[pid_str].id,
                        product_scene_image.c.scene_image_id == scene_image.id,
                    )
                    .values(is_deleted=False, deleted_at=None)
                )
            else:
                stmt = product_scene_image.insert().values(
                    product_id=product_map[pid_str].id,
                    scene_image_id=scene_image.id,
                )
                await db.execute(stmt)

    await db.commit()
    await db.refresh(scene_image)

    scene_image = await db.scalar(
        select(SceneImage)
        .options(joinedload(SceneImage.attachment), selectinload(SceneImage.products))
        .where(SceneImage.id == scene_image.id)
    )
    return {"code": 200, "data": _scene_image_response(scene_image, request)}


@router.get("/{scene_image_id}", response_model=dict, dependencies=[Depends(PermissionChecker("scene_image:view"))])
async def get_scene_image(
    request: Request,
    scene_image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SceneImage)
        .options(joinedload(SceneImage.attachment), selectinload(SceneImage.products))
        .where(SceneImage.id == scene_image_id, SceneImage.is_deleted.is_(False))
    )
    scene_image = result.scalar_one_or_none()
    if not scene_image:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "场景图不存在"})
    return {"code": 200, "data": _scene_image_response(scene_image, request)}


@router.put(
    "/{scene_image_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("scene_image:edit"))],
)
@audit_action("scene_image_update", module="scene_images")
async def update_scene_image(
    request: Request,
    scene_image_id: UUID,
    data: SceneImageUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SceneImage).where(
            SceneImage.id == scene_image_id, SceneImage.is_deleted.is_(False)
        )
    )
    scene_image = result.scalar_one_or_none()
    if not scene_image:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "场景图不存在"})

    values = data.model_dump(exclude_unset=True)
    if "attachment_id" in values and values["attachment_id"] is not None:
        attachment = await db.scalar(
            select(Attachment).where(
                Attachment.id == values["attachment_id"], Attachment.is_deleted.is_(False)
            )
        )
        if not attachment:
            raise HTTPException(status_code=404, detail={"code": 40401, "msg": "附件不存在"})
        if attachment.file_type != "image":
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "仅允许 image 类型的附件"}
            )

    for field, value in values.items():
        setattr(scene_image, field, value)

    await db.commit()
    await db.refresh(scene_image)
    return {"code": 200, "msg": "success"}


@router.delete(
    "/{scene_image_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("scene_image:delete"))],
)
@audit_action("scene_image_delete", module="scene_images")
async def delete_scene_image(
    request: Request,
    scene_image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SceneImage).where(
            SceneImage.id == scene_image_id, SceneImage.is_deleted.is_(False)
        )
    )
    scene_image = result.scalar_one_or_none()
    if not scene_image:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "场景图不存在"})

    await db.execute(
        product_scene_image.update()
        .where(product_scene_image.c.scene_image_id == scene_image_id)
        .values(is_deleted=True)
    )

    scene_image.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}


@router.post(
    "/{scene_image_id}/bind",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("scene_image:edit"))],
)
@audit_action("scene_image_bind", module="scene_images")
async def bind_products(
    request: Request,
    scene_image_id: UUID,
    data: SceneImageBind,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SceneImage).where(
            SceneImage.id == scene_image_id, SceneImage.is_deleted.is_(False)
        )
    )
    scene_image = result.scalar_one_or_none()
    if not scene_image:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "场景图不存在"})

    if not data.product_ids:
        return {"code": 200, "msg": "success"}

    products = await db.scalars(
        select(Product).where(
            Product.id.in_(data.product_ids), Product.is_deleted.is_(False)
        )
    )
    product_map = {str(p.id): p for p in products.all()}

    for pid in data.product_ids:
        pid_str = str(pid)
        if pid_str not in product_map:
            continue
        existing = await db.execute(
            select(product_scene_image).where(
                product_scene_image.c.product_id == product_map[pid_str].id,
                product_scene_image.c.scene_image_id == scene_image_id,
                product_scene_image.c.is_deleted.is_(False),
            )
        )
        if existing.scalar_one_or_none():
            continue

        current_count_result = await db.execute(
            select(func.count()).select_from(product_scene_image).where(
                product_scene_image.c.product_id == product_map[pid_str].id,
                product_scene_image.c.is_deleted.is_(False),
            )
        )
        current_count = current_count_result.scalar() or 0
        if current_count >= MAX_PRODUCT_SCENE_IMAGES:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": 42201,
                    "msg": (
                    f"产品 {product_map[pid_str].product_no} "
                    f"场景图数量已达上限（最多 {MAX_PRODUCT_SCENE_IMAGES} 张）"
                ),
                },
            )

        # 检查是否有软删除的旧记录，有则恢复
        existing_deleted = await db.execute(
            select(product_scene_image).where(
                product_scene_image.c.product_id == product_map[pid_str].id,
                product_scene_image.c.scene_image_id == scene_image_id,
                product_scene_image.c.is_deleted.is_(True),
            )
        )
        if existing_deleted.scalar_one_or_none():
            await db.execute(
                product_scene_image.update()
                .where(
                    product_scene_image.c.product_id == product_map[pid_str].id,
                    product_scene_image.c.scene_image_id == scene_image_id,
                )
                .values(is_deleted=False, deleted_at=None)
            )
        else:
            stmt = product_scene_image.insert().values(
                product_id=product_map[pid_str].id,
                scene_image_id=scene_image_id,
            )
            await db.execute(stmt)

    await db.commit()
    return {"code": 200, "msg": "success"}


@router.post(
    "/{scene_image_id}/unbind",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("scene_image:edit"))],
)
@audit_action("scene_image_unbind", module="scene_images")
async def unbind_products(
    request: Request,
    scene_image_id: UUID,
    data: SceneImageUnbind,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SceneImage).where(
            SceneImage.id == scene_image_id, SceneImage.is_deleted.is_(False)
        )
    )
    scene_image = result.scalar_one_or_none()
    if not scene_image:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "场景图不存在"})

    if not data.product_ids:
        return {"code": 200, "msg": "success"}

    products = await db.scalars(
        select(Product).where(
            Product.id.in_(data.product_ids), Product.is_deleted.is_(False)
        )
    )
    product_map = {str(p.id): p for p in products.all()}

    for pid in data.product_ids:
        pid_str = str(pid)
        if pid_str not in product_map:
            continue
        await db.execute(
            product_scene_image.update()
            .where(
                product_scene_image.c.product_id == product_map[pid_str].id,
                product_scene_image.c.scene_image_id == scene_image_id,
            )
            .values(is_deleted=True)
        )

    await db.commit()
    return {"code": 200, "msg": "success"}


@router.get(
    "/{scene_image_id}/products",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("scene_image:view"))],
)
async def get_scene_image_products(
    scene_image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SceneImage).where(
            SceneImage.id == scene_image_id, SceneImage.is_deleted.is_(False)
        )
    )
    scene_image = result.scalar_one_or_none()
    if not scene_image:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "场景图不存在"})

    product_ids_result = await db.execute(
        select(product_scene_image.c.product_id).where(
            product_scene_image.c.scene_image_id == scene_image_id,
            product_scene_image.c.is_deleted.is_(False),
        )
    )
    product_ids = [row.product_id for row in product_ids_result.all()]

    if not product_ids:
        return {"code": 200, "data": {"list": [], "total": 0}}

    products = await db.scalars(
        select(Product).where(
            Product.id.in_(product_ids), Product.is_deleted.is_(False)
        )
    )
    return {
        "code": 200,
        "data": {
            "list": [
                {
                    "id": str(p.id),
                    "product_no": p.product_no,
                    "product_name": p.product_name,
                }
                for p in products.all()
            ],
            "total": len(product_ids),
        },
    }


@router.post(
    "/batch-bind",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("scene_image:edit"))],
)
@audit_action("scene_image_batch_bind", module="scene_images")
async def batch_bind_products(
    request: Request,
    data: SceneImageBatchBind,
    db: AsyncSession = Depends(get_db),
):
    if not data.scene_image_ids or not data.product_ids:
        return {
            "code": 200,
            "data": {
                "bound_count": 0,
                "skipped_count": 0,
                "exceeded_products": [],
            },
        }

    scene_images = await db.scalars(
        select(SceneImage).where(
            SceneImage.id.in_(data.scene_image_ids),
            SceneImage.is_deleted.is_(False),
        )
    )
    scene_map = {str(s.id): s for s in scene_images.all()}

    products = await db.scalars(
        select(Product).where(
            Product.id.in_(data.product_ids),
            Product.is_deleted.is_(False),
        )
    )
    product_map = {str(p.id): p for p in products.all()}

    exceeded_products = []
    for pid in data.product_ids:
        pid_str = str(pid)
        if pid_str not in product_map:
            continue

        current_count_result = await db.execute(
            select(func.count()).select_from(product_scene_image).where(
                product_scene_image.c.product_id == product_map[pid_str].id,
                product_scene_image.c.is_deleted.is_(False),
            )
        )
        current_count = current_count_result.scalar() or 0

        new_count = 0
        for sid in data.scene_image_ids:
            sid_str = str(sid)
            if sid_str not in scene_map:
                continue
            existing = await db.execute(
                select(product_scene_image).where(
                    product_scene_image.c.product_id == product_map[pid_str].id,
                    product_scene_image.c.scene_image_id == scene_map[sid_str].id,
                    product_scene_image.c.is_deleted.is_(False),
                )
            )
            if existing.scalar_one_or_none():
                continue
            new_count += 1

        if current_count + new_count > MAX_PRODUCT_SCENE_IMAGES:
            exceeded_products.append({
                "product_id": pid_str,
                "product_no": product_map[pid_str].product_no,
                "product_name": product_map[pid_str].product_name,
                "current_count": current_count,
                "would_be": current_count + new_count,
                "limit": MAX_PRODUCT_SCENE_IMAGES,
            })

    if exceeded_products:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 42201,
                "msg": "部分产品场景图绑定后将超过上限",
                "exceeded_products": exceeded_products,
            },
        )

    bound_count = 0
    skipped_count = 0
    for pid in data.product_ids:
        pid_str = str(pid)
        if pid_str not in product_map:
            continue
        for sid in data.scene_image_ids:
            sid_str = str(sid)
            if sid_str not in scene_map:
                continue

            existing = await db.execute(
                select(product_scene_image).where(
                    product_scene_image.c.product_id == product_map[pid_str].id,
                    product_scene_image.c.scene_image_id == scene_map[sid_str].id,
                    product_scene_image.c.is_deleted.is_(False),
                )
            )
            if existing.scalar_one_or_none():
                skipped_count += 1
                continue

            existing_deleted = await db.execute(
                select(product_scene_image).where(
                    product_scene_image.c.product_id == product_map[pid_str].id,
                    product_scene_image.c.scene_image_id == scene_map[sid_str].id,
                    product_scene_image.c.is_deleted.is_(True),
                )
            )
            if existing_deleted.scalar_one_or_none():
                await db.execute(
                    product_scene_image.update()
                    .where(
                        product_scene_image.c.product_id == product_map[pid_str].id,
                        product_scene_image.c.scene_image_id == scene_map[sid_str].id,
                    )
                    .values(is_deleted=False, deleted_at=None)
                )
            else:
                await db.execute(
                    product_scene_image.insert().values(
                        product_id=product_map[pid_str].id,
                        scene_image_id=scene_map[sid_str].id,
                    )
                )
            bound_count += 1

    await db.commit()
    return {
        "code": 200,
        "data": {
            "bound_count": bound_count,
            "skipped_count": skipped_count,
            "exceeded_products": [],
        },
    }
