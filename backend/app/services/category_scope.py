"""分类作用域：把一个分类展开成「它 + 全部后代」。

多级分类导航里点「办公家具」期望看到下面所有子类目的产品，而不是只有
直接挂在一级分类上的那几件。分类表规模很小（几十到几百行），一次性读出
父子关系在内存里展开比递归 CTE 更省事，也避免不同数据库方言的差异。

软删除的分类不参与展开：它的子孙即使还挂在下面，也不应该被一级入口带出来。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.product import Category


async def category_with_descendants(db, category_id: UUID) -> list[UUID]:
    result = await db.execute(
        select(Category.id, Category.parent_id).where(Category.is_deleted.is_(False))
    )
    children: dict[UUID | None, list[UUID]] = {}
    for child_id, parent_id in result.all():
        children.setdefault(parent_id, []).append(child_id)

    scoped: list[UUID] = [category_id]
    seen: set[UUID] = {category_id}
    stack = [category_id]
    while stack:
        current = stack.pop()
        for child_id in children.get(current, []):
            if child_id in seen:
                continue
            seen.add(child_id)
            scoped.append(child_id)
            stack.append(child_id)
    return scoped
