from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.models.product import Category
from app.schemas.product import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter()


def _category_response(category: Category, children: list[CategoryResponse] | None = None):
    return CategoryResponse(
        id=category.id,
        category_name=category.category_name,
        parent_id=category.parent_id,
        sort=category.sort,
        level=category.level,
        create_time=category.create_time,
        children=children or [],
    )


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("category:view"))])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Category)
        .where(Category.is_deleted.is_(False))
        .order_by(Category.level, Category.sort)
    )
    categories = result.scalars().all()

    def build_tree(parent_id=None, level=1):
        nodes = []
        for cat in categories:
            if cat.level == level and cat.parent_id == parent_id:
                node = _category_response(cat, build_tree(cat.id, level + 1))
                nodes.append(node)
        return nodes

    return {"code": 200, "data": build_tree()}


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker("category:create"))],
)
async def create_category(category_data: CategoryCreate, db: AsyncSession = Depends(get_db)):
    level = 1
    if category_data.parent_id:
        result = await db.execute(
            select(Category).where(
                Category.id == category_data.parent_id, Category.is_deleted.is_(False)
            )
        )
        parent = result.scalar_one_or_none()
        if parent:
            level = parent.level + 1

    category = Category(
        parent_id=category_data.parent_id,
        level=level,
        category_name=category_data.category_name,
        sort=category_data.sort,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return _category_response(category)


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    dependencies=[Depends(PermissionChecker("category:edit"))],
)
async def update_category(
    category_id: UUID, category_data: CategoryUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.is_deleted.is_(False))
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "分类不存在"})

    for field, value in category_data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(category, field, value)

    await db.commit()
    await db.refresh(category)
    return _category_response(category)


@router.delete("/{category_id}", dependencies=[Depends(PermissionChecker("category:delete"))])
async def delete_category(category_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.is_deleted.is_(False))
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "分类不存在"})

    children = await db.execute(
        select(Category).where(Category.parent_id == category_id, Category.is_deleted.is_(False))
    )
    if children.scalar_one_or_none():
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "分类下存在子分类，无法删除"}
        )

    category.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}
