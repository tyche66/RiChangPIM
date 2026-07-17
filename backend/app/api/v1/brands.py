from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.models.product import Brand
from app.schemas.product import BrandBase, BrandResponse


def create_crud_router(model, create_schema, response_schema, prefix, perms):
    """生成一套通用 CRUD 路由，并挂载与权限目录一致的 PermissionChecker。

    perms 期望含 view/create/edit/delete 四个权限码，分别对应列表/新增/更新/删除。
    """
    r = APIRouter()

    @r.get("", response_model=dict, dependencies=[Depends(PermissionChecker(perms["view"]))])
    async def list_items(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(model).where(model.is_deleted.is_(False)))
        items = result.scalars().all()
        return {"code": 200, "data": {"list": [response_schema.model_validate(i) for i in items]}}

    @r.post(
        "",
        response_model=response_schema,
        status_code=201,
        dependencies=[Depends(PermissionChecker(perms["create"]))],
    )
    async def create_item(item_data: create_schema, db: AsyncSession = Depends(get_db)):
        item = model(**item_data.model_dump())
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @r.put(
        "/{item_id}",
        response_model=response_schema,
        dependencies=[Depends(PermissionChecker(perms["edit"]))],
    )
    async def update_item(
        item_id: UUID, item_data: create_schema, db: AsyncSession = Depends(get_db)
    ):
        result = await db.execute(
            select(model).where(model.id == item_id, model.is_deleted.is_(False))
        )
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail={"code": 40401, "msg": "资源不存在"})
        for field, value in item_data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(item, field, value)
        await db.commit()
        await db.refresh(item)
        return item

    @r.delete("/{item_id}", dependencies=[Depends(PermissionChecker(perms["delete"]))])
    async def delete_item(item_id: UUID, db: AsyncSession = Depends(get_db)):
        result = await db.execute(
            select(model).where(model.id == item_id, model.is_deleted.is_(False))
        )
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail={"code": 40401, "msg": "资源不存在"})
        item.is_deleted = True
        await db.commit()
        return {"code": 200, "msg": "success"}

    return r


router = create_crud_router(
    Brand,
    BrandBase,
    BrandResponse,
    "/brands",
    {
        "view": "brand:view",
        "create": "brand:create",
        "edit": "brand:edit",
        "delete": "brand:delete",
    },
)
