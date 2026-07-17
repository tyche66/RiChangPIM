from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.models.product import Tag
from app.schemas.product import TagCreate, TagResponse

router = APIRouter()


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("tag:view"))])
async def list_tags(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tag).where(Tag.is_deleted.is_(False)))
    items = result.scalars().all()
    return {"code": 200, "data": {"list": [TagResponse.model_validate(i) for i in items]}}


@router.post(
    "",
    response_model=TagResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker("tag:create"))],
)
async def create_tag(item_data: TagCreate, db: AsyncSession = Depends(get_db)):
    item = Tag(**item_data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put(
    "/{item_id}",
    response_model=TagResponse,
    dependencies=[Depends(PermissionChecker("tag:edit"))],
)
async def update_tag(item_id: UUID, item_data: TagCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tag).where(Tag.id == item_id, Tag.is_deleted.is_(False)))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "资源不存在"})
    for field, value in item_data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}", dependencies=[Depends(PermissionChecker("tag:delete"))])
async def delete_tag(item_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tag).where(Tag.id == item_id, Tag.is_deleted.is_(False)))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "资源不存在"})
    item.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}
