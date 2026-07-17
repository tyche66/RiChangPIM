"""圣奥 taxonomy 导入脚本.

用法:
    python app/scripts/import_sunon_taxonomy.py <json_path>

幂等保证:
    - Supplier「圣奥」不存在则创建，存在则复用
    - Category 按 (parent_id, category_name) 去重，存在则更新
    - Tag 按 (tag_name, tag_type='series') 去重，存在则跳过
    - 不导入 meta 中的 source/url/account 等元数据
    - 仅输出计数，不泄露任何密钥或连接信息
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

# 解析到 backend/ 项目根，不依赖启动目录（CWD）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Pure layer — no DB imports, fully unit-testable
# ---------------------------------------------------------------------------


class TaxonomyValidationError(Exception):
    """输入 JSON 结构校验失败时抛出."""


def normalize_name(name: str) -> str:
    """去除首尾空白，压缩中间连续空白."""
    return " ".join(str(name).split())


def validate_and_normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """校验并标准化 taxonomy JSON.

    返回:
        {
            "categories": {
                <l1_name>: {
                    "name": <normalized>,
                    "children": [<normalized l2 names>],
                }
            },
            "series": [<normalized series names>],
        }

    重复的 L2 子项名在标准化后会被去重（保留首次出现顺序）.
    """
    if not isinstance(raw, dict):
        raise TaxonomyValidationError("顶层必须是 JSON 对象")

    raw_categories = raw.get("大类")
    raw_series = raw.get("系列_品牌")

    if not isinstance(raw_categories, dict):
        raise TaxonomyValidationError('"大类" 字段缺失或不是对象')
    if not isinstance(raw_series, list):
        raise TaxonomyValidationError('"系列_品牌" 字段缺失或不是数组')

    categories: dict[str, dict[str, Any]] = {}
    for l1_raw, l1_data in raw_categories.items():
        l1_name = normalize_name(l1_raw)
        if not l1_name:
            continue
        if not isinstance(l1_data, dict):
            raise TaxonomyValidationError(f'大类 "{l1_name}" 的值必须是对象')
        raw_children = l1_data.get("小类", [])
        if not isinstance(raw_children, list):
            raise TaxonomyValidationError(f'大类 "{l1_name}" 的 "小类" 必须是数组')
        seen: set[str] = set()
        children: list[str] = []
        for child_raw in raw_children:
            child = normalize_name(child_raw)
            if not child:
                continue
            if child not in seen:
                seen.add(child)
                children.append(child)
        if l1_name in categories:
            # 合并已有大类下的子项（去重）
            existing = categories[l1_name]["children"]
            for c in children:
                if c not in existing:
                    existing.append(c)
        else:
            categories[l1_name] = {"name": l1_name, "children": children}

    series = []
    seen_series: set[str] = set()
    for s_raw in raw_series:
        s = normalize_name(s_raw)
        if s and s not in seen_series:
            seen_series.add(s)
            series.append(s)

    return {"categories": categories, "series": series}


# ---------------------------------------------------------------------------
# DB layer — async, idempotent upsert
# ---------------------------------------------------------------------------


SUPPLIER_NAME = "圣奥"
TAG_TYPE_SERIES = "series"


async def _get_or_create_supplier(db: AsyncSession) -> Any:
    """幂等获取或创建 Supplier「圣奥」."""
    from app.models.product import Supplier

    result = await db.execute(select(Supplier).where(Supplier.supplier_name == SUPPLIER_NAME))
    supplier = result.scalar_one_or_none()
    if supplier:
        return supplier, False

    supplier = Supplier(
        id=uuid4(),
        supplier_name=SUPPLIER_NAME,
        contact=None,
        phone=None,
        cooperation_status="active",
    )
    db.add(supplier)
    await db.flush()
    return supplier, True


async def _get_or_create_category(
    db: AsyncSession, name: str, parent_id: Any | None, level: int
) -> tuple[Any, bool]:
    """幂等获取或创建 Category.

    唯一键: (parent_id, category_name).
    若同名同 parent 已存在则返回现有记录（updated=False）.
    """
    from app.models.product import Category

    stmt = select(Category).where(
        Category.category_name == name,
        Category.level == level,
        Category.parent_id == parent_id,
        Category.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    cat = result.scalar_one_or_none()
    if cat:
        return cat, False

    cat = Category(
        id=uuid4(),
        parent_id=parent_id,
        level=level,
        category_name=name,
        sort=0,
    )
    db.add(cat)
    await db.flush()
    return cat, True


async def _get_or_create_tag(db: AsyncSession, name: str, tag_type: str) -> tuple[Any, bool]:
    """幂等获取或创建 Tag.

    唯一键: (tag_name, tag_type).
    """
    from app.models.product import Tag

    stmt = select(Tag).where(
        Tag.tag_name == name,
        Tag.tag_type == tag_type,
        Tag.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    tag = result.scalar_one_or_none()
    if tag:
        return tag, False

    tag = Tag(
        id=uuid4(),
        tag_name=name,
        tag_type=tag_type,
    )
    db.add(tag)
    await db.flush()
    return tag, True


async def import_taxonomy(db: AsyncSession, data: dict[str, Any]) -> dict[str, int]:
    """将已校验的 taxonomy 数据导入 DB.

    返回计数:
        {
            "supplier_created": 0|1,
            "categories_l1_created": N,
            "categories_l1_existing": N,
            "categories_l2_created": N,
            "categories_l2_existing": N,
            "tags_series_created": N,
            "tags_series_existing": N,
        }
    """
    counts: dict[str, int] = {
        "supplier_created": 0,
        "categories_l1_created": 0,
        "categories_l1_existing": 0,
        "categories_l2_created": 0,
        "categories_l2_existing": 0,
        "tags_series_created": 0,
        "tags_series_existing": 0,
    }

    supplier, sup_created = await _get_or_create_supplier(db)
    counts["supplier_created"] = 1 if sup_created else 0

    # Categories
    for l1_info in data["categories"].values():
        l1_name = l1_info["name"]
        l1_cat, l1_created = await _get_or_create_category(db, l1_name, None, 1)
        if l1_created:
            counts["categories_l1_created"] += 1
        else:
            counts["categories_l1_existing"] += 1

        for child_name in l1_info["children"]:
            _, l2_created = await _get_or_create_category(db, child_name, l1_cat.id, 2)
            if l2_created:
                counts["categories_l2_created"] += 1
            else:
                counts["categories_l2_existing"] += 1

    # Series tags
    for series_name in data["series"]:
        _, tag_created = await _get_or_create_tag(db, series_name, TAG_TYPE_SERIES)
        if tag_created:
            counts["tags_series_created"] += 1
        else:
            counts["tags_series_existing"] += 1

    return counts


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _print_counts(counts: dict[str, int]) -> None:
    print(f"Supplier '{SUPPLIER_NAME}': created={counts['supplier_created']}")
    print(
        f"Categories L1: created={counts['categories_l1_created']}, "
        f"existing={counts['categories_l1_existing']}"
    )
    print(
        f"Categories L2: created={counts['categories_l2_created']}, "
        f"existing={counts['categories_l2_existing']}"
    )
    print(
        f"Tags (series): created={counts['tags_series_created']}, "
        f"existing={counts['tags_series_existing']}"
    )


async def _async_main(json_path: str) -> None:
    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    data = validate_and_normalize(raw)

    # Register models referenced by string relationships before the first ORM query.
    import app.models.doc_chunk  # noqa: F401
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        counts = await import_taxonomy(db, data)
        await db.commit()

    _print_counts(counts)


def main() -> None:
    parser = argparse.ArgumentParser(description="导入圣奥 taxonomy（品类 + 系列）到 PIM")
    parser.add_argument("json_path", help="classification JSON 文件路径")
    args = parser.parse_args()

    if not os.path.isfile(args.json_path):
        print(f"error: file not found: {args.json_path}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(_async_main(args.json_path))


if __name__ == "__main__":
    main()
