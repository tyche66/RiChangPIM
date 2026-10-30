"""产品列表的六维度筛选选项（二级 / 三级）。

菜单数据一律从产品表和关联表算出来，不写死枚举、不引入示例分类：
没有产品的选项天然不会出现，计数也和筛选结果同源（同一套 SQL 条件）。

口径说明：

* 一级维度：``series`` / ``brand`` / ``supplier`` / ``status`` / ``stock`` / ``category``；
* 二级：
  - series / category —— 产品所在分类（含后代计数，与筛选口径一致）；
  - brand / supplier —— 品牌 / 供应商本身；
  - status / stock —— 枚举值；
* 三级：
  - series —— 该分类范围内产品身上的系列标签（``tag_type='series'``）；
  - brand / supplier —— 该品牌 / 供应商产品实际落在的分类；
  - category —— 该分类范围内产品的规格长度（``1200*600*750`` 的第一段）；
  - status / stock —— 无三级。

「系列 → 办公桌 → 大都会」与「品类 → 办公桌 → 1800」走的是两套不同的三级数据源，
同名二级分类不会串数据。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, select

from app.models.product import Brand, Category, Product, ProductTag, Supplier, Tag
from app.services.category_scope import category_with_descendants
from app.services.specification import format_spec_length, parse_spec_length_mm

DIMENSIONS = ("series", "brand", "supplier", "status", "stock", "category")

#: 二级是枚举的维度不需要三级菜单。
FLAT_DIMENSIONS = ("status", "stock")

STATUS_LABELS = {"active": "上架", "inactive": "下架", "draft": "草稿"}
STOCK_LABELS = {
    "in_stock": "有货",
    "out_of_stock": "缺货",
    "preorder": "预售",
    "unknown": "未知",
}

#: 规格长度选项最多返回多少个（按长度升序），避免一个分类铺出上百个标签。
MAX_SPEC_OPTIONS = 60


class FilterOptionError(ValueError):
    """请求的维度 / 上级参数不合法。"""


def _item(value: str, label: str, count: int) -> dict:
    return {"value": value, "label": label, "count": count}


def _parse_parent(parent_id: str | None) -> UUID:
    if not parent_id:
        raise FilterOptionError("缺少上级筛选值")
    try:
        return UUID(parent_id)
    except ValueError as exc:
        raise FilterOptionError("上级筛选值格式无效") from exc


async def list_filter_options(
    db, *, dimension: str, parent_id: str | None = None
) -> list[dict]:
    if dimension not in DIMENSIONS:
        raise FilterOptionError(f"不支持的筛选维度：{dimension}")
    if dimension in FLAT_DIMENSIONS:
        return await _enum_options(
            db,
            Product.status if dimension == "status" else Product.stock_status,
            STATUS_LABELS if dimension == "status" else STOCK_LABELS,
        )
    if dimension == "series":
        if parent_id:
            return await _series_tags(db, _parse_parent(parent_id))
        return await _category_options(db, require_series=True)
    if dimension == "brand":
        if parent_id:
            return await _category_options_of(db, brand_id=_parse_parent(parent_id))
        return await _relation_options(db, Brand, Brand.brand_name, Product.brand_id)
    if dimension == "supplier":
        if parent_id:
            return await _category_options_of(db, supplier_id=_parse_parent(parent_id))
        return await _relation_options(db, Supplier, Supplier.supplier_name, Product.supplier_id)
    # category
    if parent_id:
        return await _spec_options(db, _parse_parent(parent_id))
    return await _category_options(db, require_series=False)


# ---------------------------------------------------------------------------
# 分类树
# ---------------------------------------------------------------------------
async def _category_rows(db) -> list[tuple[UUID, str, UUID | None]]:
    result = await db.execute(
        select(Category.id, Category.category_name, Category.parent_id).where(
            Category.is_deleted.is_(False)
        )
    )
    return [(row[0], row[1], row[2]) for row in result.all()]


def _roll_up(counts: dict[UUID, int], parents: dict[UUID, UUID | None]) -> dict[UUID, int]:
    """把「直接挂在该分类上的产品数」沿父链累加，得到含后代的计数。"""
    rolled = dict(counts)
    for category_id, count in counts.items():
        seen = {category_id}
        parent = parents.get(category_id)
        while parent and parent not in seen:
            seen.add(parent)
            rolled[parent] = rolled.get(parent, 0) + count
            parent = parents.get(parent)
    return rolled


async def _category_options(db, *, require_series: bool) -> list[dict]:
    rows = await _category_rows(db)
    names = {cid: name for cid, name, _ in rows}
    parents = {cid: parent for cid, _, parent in rows}

    stmt = select(Product.category_id, func.count(func.distinct(Product.id))).where(
        Product.is_deleted.is_(False)
    )
    if require_series:
        stmt = stmt.join(
            ProductTag,
            and_(ProductTag.product_id == Product.id, ProductTag.is_deleted.is_(False)),
        ).join(
            Tag,
            and_(
                Tag.id == ProductTag.tag_id,
                Tag.is_deleted.is_(False),
                Tag.tag_type == "series",
            ),
        )
    stmt = stmt.group_by(Product.category_id)

    counts = {
        category_id: count
        for category_id, count in (await db.execute(stmt)).all()
        if category_id is not None
    }
    rolled = _roll_up(counts, parents)
    items = [
        _item(str(category_id), names[category_id], count)
        for category_id, count in rolled.items()
        if category_id in names and count > 0
    ]
    items.sort(key=lambda item: (-item["count"], item["label"]))
    return items


async def _category_options_of(
    db, *, brand_id: UUID | None = None, supplier_id: UUID | None = None
) -> list[dict]:
    """某个品牌 / 供应商的产品实际落在哪些分类（二级选择后的三级）。"""
    rows = await _category_rows(db)
    names = {cid: name for cid, name, _ in rows}

    stmt = select(Product.category_id, func.count(func.distinct(Product.id))).where(
        Product.is_deleted.is_(False)
    )
    if brand_id is not None:
        stmt = stmt.where(Product.brand_id == brand_id)
    if supplier_id is not None:
        stmt = stmt.where(Product.supplier_id == supplier_id)
    stmt = stmt.group_by(Product.category_id)

    items = [
        _item(str(category_id), names[category_id], count)
        for category_id, count in (await db.execute(stmt)).all()
        if category_id in names
    ]
    items.sort(key=lambda item: (-item["count"], item["label"]))
    return items


async def _series_tags(db, category_id: UUID) -> list[dict]:
    scope = await category_with_descendants(db, category_id)
    count_expr = func.count(func.distinct(Product.id))
    stmt = (
        select(Tag.id, Tag.tag_name, count_expr)
        .select_from(Product)
        .join(
            ProductTag,
            and_(ProductTag.product_id == Product.id, ProductTag.is_deleted.is_(False)),
        )
        .join(Tag, and_(Tag.id == ProductTag.tag_id, Tag.is_deleted.is_(False)))
        .where(
            Product.is_deleted.is_(False),
            Product.category_id.in_(scope),
            Tag.tag_type == "series",
        )
        .group_by(Tag.id, Tag.tag_name)
        .order_by(count_expr.desc(), Tag.tag_name.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [_item(str(tag_id), name, count) for tag_id, name, count in rows]


async def _spec_options(db, category_id: UUID) -> list[dict]:
    """品类三级：该分类范围内真实出现的规格长度（``1200*600*750`` → 1200）。

    聚合放在 Python 里做：库里规格写法不统一（``W2000*1000*750`` / ``L1000``），
    SQL 直接强转会报错；同分类下的不同规格原值数量很少，一次取回再分组足够快。
    """
    scope = await category_with_descendants(db, category_id)
    stmt = (
        select(Product.specification, func.count(func.distinct(Product.id)))
        .where(
            Product.is_deleted.is_(False),
            Product.category_id.in_(scope),
            Product.specification.is_not(None),
        )
        .group_by(Product.specification)
    )
    buckets: dict[float, int] = {}
    for specification, count in (await db.execute(stmt)).all():
        length = parse_spec_length_mm(specification)
        if length is None:
            continue
        buckets[length] = buckets.get(length, 0) + count

    items = [
        _item(format_spec_length(length), format_spec_length(length), count)
        for length, count in sorted(buckets.items())
    ]
    return items[:MAX_SPEC_OPTIONS]


async def specification_values_for(db, length: float) -> list[str]:
    """把「长度」还原成规格原值集合，供列表/导出做精确 IN 过滤。

    与 :func:`_spec_options` 用同一个解析函数，所以菜单上显示的数量和点进去的
    结果条数一致；解析不出来的规格（``异形``、``/``）不会混进任何长度档。
    """
    stmt = (
        select(Product.specification)
        .where(Product.is_deleted.is_(False), Product.specification.is_not(None))
        .distinct()
    )
    return [
        specification
        for (specification,) in (await db.execute(stmt)).all()
        if parse_spec_length_mm(specification) == length
    ]


# ---------------------------------------------------------------------------
# 品牌 / 供应商 / 枚举
# ---------------------------------------------------------------------------
async def _relation_options(db, model, name_column, fk_column) -> list[dict]:
    count_expr = func.count(func.distinct(Product.id))
    stmt = (
        select(model.id, name_column, count_expr)
        .select_from(Product)
        .join(model, model.id == fk_column)
        .where(Product.is_deleted.is_(False), model.is_deleted.is_(False))
        .group_by(model.id, name_column)
        .order_by(count_expr.desc(), name_column.asc())
    )
    return [_item(str(ident), name, count) for ident, name, count in (await db.execute(stmt)).all()]


async def _enum_options(db, column, labels: dict[str, str]) -> list[dict]:
    count_expr = func.count(func.distinct(Product.id))
    stmt = (
        select(column, count_expr)
        .where(Product.is_deleted.is_(False), column.is_not(None))
        .group_by(column)
        .order_by(count_expr.desc())
    )
    items = [
        _item(str(value), labels.get(str(value), str(value)), count)
        for value, count in (await db.execute(stmt)).all()
    ]
    items.sort(key=lambda item: (-item["count"], item["label"]))
    return items
