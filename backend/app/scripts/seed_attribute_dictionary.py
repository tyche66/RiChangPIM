"""属性词典种子（Track A）。

幂等地写入默认属性定义、取值与中文同义词，并（可选）从 Category 树
生成 ``category`` 属性的选项，使「弧形会议桌」这类品类+形状查询可用。

规则解析器与模型规划器都只认这里的数据，不再有任何写死的业务词表。

用法::

    python -m app.scripts.seed_attribute_dictionary --check
    python -m app.scripts.seed_attribute_dictionary --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.catalog_attribute import (  # noqa: E402
    CatalogAttributeAlias,
    CatalogAttributeDefinition,
    CatalogAttributeOption,
)
from app.models.product import Category  # noqa: E402

# (code, name, data_type, multi_value, searchable, hard_filterable, sort_order)
DEFINITIONS = [
    ("category", "类目", "option", True, True, True, 10),
    ("shape", "桌形", "option", False, True, True, 20),
    ("style", "风格", "option", False, True, True, 30),
    ("material", "材质", "option", True, True, True, 40),
    ("color", "颜色", "option", True, True, True, 50),
    ("series", "系列", "option", False, True, True, 60),
    ("face_price", "面价", "number", False, True, True, 70),
    ("specification_length_mm", "长度", "number", False, True, True, 80),
    ("specification_width_mm", "宽度", "number", False, True, True, 90),
    ("specification_height_mm", "高度", "number", False, True, True, 100),
    ("seat_count", "容纳人数", "number", False, True, True, 110),
]

# attribute_code -> [(option_code, label, [aliases...])]
OPTIONS: dict[str, list[tuple[str, str, list[str]]]] = {
    "shape": [
        ("arc", "弧形", ["弧形", "弧型", "圆弧", "圆弧形", "圆弧型", "弧形桌", "弧型桌"]),
        ("rect", "矩形", ["矩形", "长方形", "长方型", "方形", "长桌"]),
        ("round", "圆形", ["圆形", "圆型", "圆桌"]),
        ("oval", "椭圆形", ["椭圆形", "椭圆型", "椭圆"]),
        ("water_drop", "水滴形", ["水滴形", "水滴型", "水滴"]),
    ],
    "style": [
        ("modern", "现代", ["现代", "简约", "现代简约"]),
        ("new_chinese", "新中式", ["新中式", "中式", "新中式风格"]),
        ("nordic", "北欧", ["北欧", "北欧风"]),
        ("industrial", "工业风", ["工业风", "工业"]),
    ],
    "material": [
        ("solid_wood", "实木", ["实木", "全实木", "原木"]),
        ("board", "板材", ["板材", "中纤板", "刨花板", "密度板"]),
        ("steel", "钢制", ["钢制", "钢", "不锈钢", "冷轧钢"]),
        ("aluminium", "铝合金", ["铝合金", "铝", "铝材"]),
        ("glass", "玻璃", ["玻璃", "钢化玻璃"]),
        ("leather", "皮革", ["皮革", "真皮", "仿皮", "pu"]),
        ("fabric", "布艺", ["布艺", "面料", "织物"]),
    ],
    "color": [
        ("black", "黑色", ["黑色", "黑"]),
        ("white", "白色", ["白色", "白"]),
        ("walnut", "胡桃木", ["胡桃木", "胡桃"]),
        ("white_oak", "白橡木", ["白橡木", "白橡"]),
        ("grey", "灰色", ["灰色", "灰", "岩石灰", "流星灰"]),
        ("blue", "蓝色", ["蓝色", "蓝"]),
        ("green", "绿色", ["绿色", "绿"]),
        ("beige", "米色", ["米色", "米白", "浅色"]),
    ],
}


def _now() -> datetime:
    return datetime.now(UTC)


async def _ensure_definition(
    db, code, name, data_type, multi_value, searchable, hard_filterable, sort_order
) -> tuple[bool, CatalogAttributeDefinition]:
    row = (
        (
            await db.execute(
                select(CatalogAttributeDefinition).where(
                    CatalogAttributeDefinition.code == code,
                    CatalogAttributeDefinition.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .first()
    )
    if row is not None:
        return False, row
    row = CatalogAttributeDefinition(
        id=uuid4(), code=code, name=name, data_type=data_type,
        multi_value=multi_value, searchable=searchable,
        hard_filterable=hard_filterable, enabled=True, sort_order=sort_order,
        create_time=_now(), update_time=_now(),
    )
    db.add(row)
    return True, row


async def _ensure_option(
    db, definition, code, label, sort_order
) -> tuple[bool, CatalogAttributeOption]:
    row = (
        (
            await db.execute(
                select(CatalogAttributeOption).where(
                    CatalogAttributeOption.attribute_id == definition.id,
                    CatalogAttributeOption.code == code,
                    CatalogAttributeOption.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .first()
    )
    if row is not None:
        return False, row
    row = CatalogAttributeOption(
        id=uuid4(), attribute_id=definition.id, code=code, label=label,
        enabled=True, sort_order=sort_order, create_time=_now(), update_time=_now(),
    )
    db.add(row)
    return True, row


async def _ensure_alias(db, option, alias, source) -> bool:
    from app.knowledge.attributes import normalize_text

    normalized = normalize_text(alias)
    if not normalized:
        return False
    row = (
        (
            await db.execute(
                select(CatalogAttributeAlias).where(
                    CatalogAttributeAlias.option_id == option.id,
                    CatalogAttributeAlias.normalized_alias == normalized,
                )
            )
        )
        .scalars()
        .first()
    )
    if row is not None:
        return False
    db.add(
        CatalogAttributeAlias(
            id=uuid4(), option_id=option.id, alias=alias,
            normalized_alias=normalized, source=source, enabled=True,
            create_time=_now(), update_time=_now(),
        )
    )
    return True


async def run(*, apply: bool, include_categories: bool) -> int:
    created_definitions = created_options = created_aliases = 0
    created_categories = 0

    async with AsyncSessionLocal() as db:
        # Serialize concurrent backend replicas; rows are committed as one seed batch.
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": "ai_pim_attribute_dictionary_seed"},
        )
        for spec in DEFINITIONS:
            code, name, data_type, multi_value, searchable, hard_filterable, sort_order = spec
            made, definition = await _ensure_definition(
                db, code, name, data_type, multi_value, searchable,
                hard_filterable, sort_order,
            )
            created_definitions += int(made)

        for attribute_code, entries in OPTIONS.items():
            definition = (
                (
                    await db.execute(
                        select(CatalogAttributeDefinition).where(
                            CatalogAttributeDefinition.code == attribute_code,
                            CatalogAttributeDefinition.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if definition is None:
                continue
            for sort_order, (option_code, label, aliases) in enumerate(entries):
                made_option, option = await _ensure_option(
                    db, definition, option_code, label, sort_order
                )
                created_options += int(made_option)
                for alias in aliases:
                    made_alias = await _ensure_alias(db, option, alias, "seed")
                    created_aliases += int(made_alias)

        if include_categories:
            category_definition = (
                (
                    await db.execute(
                        select(CatalogAttributeDefinition).where(
                            CatalogAttributeDefinition.code == "category",
                            CatalogAttributeDefinition.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .first()
            )
            categories = (
                (
                    await db.execute(
                        select(Category)
                        .where(Category.is_deleted.is_(False))
                        .order_by(Category.level, Category.sort, Category.category_name)
                    )
                )
                .scalars()
                .all()
            )
            for index, category in enumerate(categories):
                # option code 用类目名（category_name），使 _category_predicate
                # 的"按名字递归取子孙类目"能直接匹配。
                made, option = await _ensure_option(
                    db, category_definition, category.category_name, category.category_name, index
                )
                created_categories += int(made)
                made_alias = await _ensure_alias(
                    db, option, category.category_name, "category_tree"
                )
                created_aliases += int(made_alias)

        if apply:
            await db.commit()

    mode = "APPLY" if apply else "CHECK"
    print(
        f"[{mode}] definitions={created_definitions} options={created_options} "
        f"aliases={created_aliases} category_options={created_categories}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="属性词典种子（幂等）")
    parser.add_argument("--check", action="store_true", help="只读预览（默认）")
    parser.add_argument("--apply", action="store_true", help="写入数据库")
    parser.add_argument(
        "--no-categories",
        action="store_true",
        help="不从 Category 树生成 category 选项",
    )
    args = parser.parse_args(argv)
    apply = bool(args.apply)
    return asyncio.run(run(apply=apply, include_categories=not args.no_categories))


if __name__ == "__main__":
    raise SystemExit(main())
