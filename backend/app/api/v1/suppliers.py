from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.models.product import Supplier
from app.schemas.product import SupplierCreate, SupplierResponse

router = APIRouter()


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("supplier:view"))])
async def list_suppliers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Supplier).where(Supplier.is_deleted.is_(False)))
    items = result.scalars().all()
    return {"code": 200, "data": {"list": [SupplierResponse.model_validate(i) for i in items]}}


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker("supplier:create"))],
)
async def create_supplier(item_data: SupplierCreate, db: AsyncSession = Depends(get_db)):
    item = Supplier(**item_data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put(
    "/{item_id}",
    response_model=SupplierResponse,
    dependencies=[Depends(PermissionChecker("supplier:edit"))],
)
async def update_supplier(
    item_id: UUID, item_data: SupplierCreate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Supplier).where(Supplier.id == item_id, Supplier.is_deleted.is_(False))
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


@router.delete("/{item_id}", dependencies=[Depends(PermissionChecker("supplier:delete"))])
async def delete_supplier(item_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Supplier).where(Supplier.id == item_id, Supplier.is_deleted.is_(False))
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "资源不存在"})
    item.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}
