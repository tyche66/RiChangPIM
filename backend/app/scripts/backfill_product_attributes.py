"""产品属性回填脚本（Track A）。

把业务确认过的产品属性写进 ``product_attribute_value``。

设计约束：
* **不从** material / description / specification 推断 shape —— 桌形只能来自
  业务确认的 mapping 文件；
* mapping 文件独立维护（``app/scripts/data/product_attribute_mapping.json``），
  脚本里不硬编码任何 SKU；
* 幂等：同一 (product, attribute, option) 重复执行不会产生第二行；
* ``--check`` 只读预览；``--apply`` 才写库，且仅用于本地或明确批准的环境；
* 生产环境只生成审计结果与待批准脚本，绝不自动写生产库。

用法::

    # 只读预览（默认）
    python -m app.scripts.backfill_product_attributes --check

    # 指定 mapping 文件
    python -m app.scripts.backfill_product_attributes --apply \\
        --mapping app/scripts/data/product_attribute_mapping.json

    # 干跑 + 指定数据库（CI/预发）
    ALEMBIC_OVERRIDE_URL=postgresql://... python -m app.scripts.backfill_product_attributes --check
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

if __package__ in (None, ""):  # 允许 `python path/to/script.py` 直接运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.catalog_attribute import (  # noqa: E402
    CatalogAttributeDefinition,
    CatalogAttributeOption,
    ProductAttributeValue,
)
from app.models.product import Product  # noqa: E402

DEFAULT_MAPPING = Path(__file__).resolve().parent / "data" / "product_attribute_mapping.json"

REQUIRED_KEYS = ("attribute_code", "option_code")
# 条目定位方式二选一：product_no（单个 SKU）或 series（系列 tag_name，可加 category_name 限定类目）
ENTRY_KEY_MODES = (("product_no",), ("series",))


def load_mapping(path: Path) -> list[dict]:
    """读取并校验 mapping 文件。

    条目支持两种定位方式：
    * ``product_no``：单个 SKU（既有格式）；
    * ``series``（+ 可选 ``category_name``）：系列单位，执行时按
      ``product_tag`` 展开到该系列（可选限定类目）的全部在售产品。
    """
    if not path.exists():
        raise SystemExit(f"mapping 文件不存在: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("mappings") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise SystemExit("mapping 文件格式错误：缺少 mappings 数组")
    out: list[dict] = []
    for index, entry in enumerate(entries):
        missing = [key for key in REQUIRED_KEYS if not entry.get(key)]
        if missing:
            raise SystemExit(f"mapping 第 {index} 条缺少字段: {missing}")
        has_product_no = bool(str(entry.get("product_no") or "").strip())
        has_series = bool(str(entry.get("series") or "").strip())
        if not has_product_no and not has_series:
            raise SystemExit(f"mapping 第 {index} 条既无 product_no 也无 series")
        out.append(
            {
                "product_no": str(entry["product_no"]).strip() if has_product_no else None,
                "series": str(entry["series"]).strip() if has_series else None,
                "category_name": (
                    str(entry["category_name"]).strip() if entry.get("category_name") else None
                ),
                "attribute_code": str(entry["attribute_code"]).strip(),
                "option_code": str(entry["option_code"]).strip(),
                "source": str(entry.get("source") or "business_confirmed"),
                "verified": bool(entry.get("verified", True)),
                "confidence": entry.get("confidence"),
                "note": entry.get("note"),
            }
        )
    return out


async def _expand_series_entries(db, entries: list[dict]) -> tuple[list[dict], list[str]]:
    """把 series 条目展开为 product_no 条目；返回 (展开后条目, 未解析系列列表)。"""
    series_specs = [
        (e["series"], e["category_name"])
        for e in entries
        if e["product_no"] is None and e["series"]
    ]
    if not series_specs:
        return entries, []

    # 系列 tag_name -> tag id（tag_type=series）
    from app.models.product import Category, ProductTag, Tag  # noqa: PLC0415

    series_names = sorted({name for name, _ in series_specs})
    tag_rows = (
        (
            await db.execute(
                select(Tag).where(
                    Tag.tag_name.in_(series_names),
                    Tag.tag_type == "series",
                    Tag.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    tag_by_name = {row.tag_name: row for row in tag_rows}
    unresolved = [name for name in series_names if name not in tag_by_name]
    if unresolved:
        return entries, unresolved

    # 每个 (系列, 类目) 的产品编号列表
    product_nos_by_spec: dict[tuple[str, str | None], list[str]] = {}
    for name, category_name in series_specs:
        tag = tag_by_name[name]
        stmt = (
            select(Product.product_no)
            .join(ProductTag, ProductTag.product_id == Product.id)
            .join(Category, Category.id == Product.category_id)
            .where(
                ProductTag.tag_id == tag.id,
                ProductTag.is_deleted.is_(False),
                Product.is_deleted.is_(False),
                Product.status == "active",
            )
        )
        if category_name:
            stmt = stmt.where(Category.category_name == category_name)
        rows = (await db.execute(stmt)).scalars().all()
        product_nos_by_spec[(name, category_name)] = sorted(rows)

    expanded: list[dict] = []
    for entry in entries:
        if entry["product_no"] is not None:
            expanded.append(entry)
            continue
        name = entry["series"]
        if name not in tag_by_name:
            continue
        category_name = entry["category_name"]
        nos = product_nos_by_spec.get((name, category_name), [])
        if not nos:
            scope = f"{name}系列" + (f"/{category_name}" if category_name else "")
            print(f"[check] WARN 系列展开为空（无在售产品）: {scope}")
            continue
        for product_no in nos:
            child = dict(entry)
            child["product_no"] = product_no
            child["series"] = None
            note = child.get("note") or ""
            scope = f"{name}系列" + (f"/{category_name}" if category_name else "")
            child["note"] = f"[系列展开:{scope}] {note}".strip()
            expanded.append(child)
    return expanded, []


async def _resolve_products(db, product_nos: list[str]) -> dict[str, Product]:
    rows = (
        (
            await db.execute(
                select(Product).where(
                    Product.product_no.in_(product_nos),
                    Product.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.product_no: row for row in rows}


async def _resolve_options(
    db, pairs: list[tuple[str, str]]
) -> dict[tuple[str, str], tuple[CatalogAttributeDefinition, CatalogAttributeOption]]:
    codes = sorted({attribute for attribute, _ in pairs})
    definitions = (
        (
            await db.execute(
                select(CatalogAttributeDefinition).where(
                    CatalogAttributeDefinition.code.in_(codes),
                    CatalogAttributeDefinition.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    option_codes = sorted({option for _, option in pairs})
    options = (
        (
            await db.execute(
                select(CatalogAttributeOption).where(
                    CatalogAttributeOption.code.in_(option_codes),
                    CatalogAttributeOption.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    definition_by_id = {row.id: row for row in definitions}
    out: dict[tuple[str, str], tuple] = {}
    for option in options:
        definition = definition_by_id.get(option.attribute_id)
        if definition is None:
            continue
        out[(definition.code, option.code)] = (definition, option)
    return out


async def _existing_values(db, product_ids) -> set[tuple]:
    rows = (
        (
            await db.execute(
                select(ProductAttributeValue).where(
                    ProductAttributeValue.product_id.in_(product_ids),
                    ProductAttributeValue.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    return {(row.product_id, row.attribute_id, row.option_id, row.value_text) for row in rows}


async def run(mapping_path: Path, *, apply: bool) -> int:
    entries = load_mapping(mapping_path)
    if not entries:
        print("[check] mapping 为空，无需回填")
        return 0

    async with AsyncSessionLocal() as db:
        entries, unresolved_series = await _expand_series_entries(db, entries)
        for name in unresolved_series:
            print(f"[check] UNRESOLVED 系列不存在或未标注: {name}")
        if not entries:
            print("[check] 展开后无有效条目")
            return 0

        product_nos = sorted({entry["product_no"] for entry in entries if entry["product_no"]})
        pairs = [(entry["attribute_code"], entry["option_code"]) for entry in entries]

        created = 0
        skipped = 0
        unresolved: list[str] = []

        products = await _resolve_products(db, product_nos)
        resolved = await _resolve_options(db, pairs)
        existing = await _existing_values(db, list(p.id for p in products.values()))

        for entry in entries:
            key = (entry["attribute_code"], entry["option_code"])
            product = products.get(entry["product_no"])
            if product is None:
                unresolved.append(f"产品不存在或已删除: {entry['product_no']}")
                continue
            resolved_pair = resolved.get(key)
            if resolved_pair is None:
                unresolved.append(
                    f"属性/取值未定义: {entry['attribute_code']}={entry['option_code']}"
                )
                continue
            definition, option = resolved_pair
            signature = (product.id, definition.id, option.id, None)
            if signature in existing:
                skipped += 1
                print(
                    f"[skip] {entry['product_no']} 已有 "
                    f"{entry['attribute_code']}={entry['option_code']}"
                )
                continue
            if not apply:
                print(
                    f"[plan] {entry['product_no']} -> "
                    f"{entry['attribute_code']}={entry['option_code']} "
                    f"(source={entry['source']}, verified={entry['verified']})"
                )
                created += 1
                continue
            db.add(
                ProductAttributeValue(
                    id=uuid4(),
                    product_id=product.id,
                    attribute_id=definition.id,
                    option_id=option.id,
                    source=entry["source"],
                    verified=entry["verified"],
                    confidence=entry["confidence"],
                    note=entry["note"],
                    create_time=datetime.now(UTC),
                    update_time=datetime.now(UTC),
                )
            )
            existing.add(signature)
            created += 1
            print(
                f"[apply] {entry['product_no']} -> {entry['attribute_code']}={entry['option_code']}"
            )
        if apply:
            await db.commit()

    mode = "APPLY" if apply else "CHECK"
    print(f"[{mode}] summary created={created} skipped={skipped} unresolved={len(unresolved)}")
    for line in unresolved:
        print(f"[{mode}] UNRESOLVED {line}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="产品属性回填（业务确认）")
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING), help="mapping JSON 路径")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="只读预览（默认）")
    group.add_argument("--apply", action="store_true", help="写入数据库")
    args = parser.parse_args(argv)

    apply = bool(args.apply)
    if not apply and os.environ.get("PIM_ALLOW_APPLY") == "1":
        apply = True
    return asyncio.run(run(Path(args.mapping), apply=apply))


if __name__ == "__main__":
    raise SystemExit(main())
