"""Idempotently import traceable Sunon pilot products from a reviewed JSON file."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

import app.models.doc_chunk  # noqa: F401 - register relationship targets
from app.core.database import AsyncSessionLocal
from app.models.product import (
    Brand,
    Category,
    Product,
    ProductTag,
    Supplier,
    Tag,
)

REQUIRED_FIELDS = {
    "product_no",
    "product_name",
    "brand_name",
    "supplier_name",
    "category_parent",
    "category_name",
    "series",
    "data_source",
    "face_price",
}


def validate_records(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("产品数据必须是非空 JSON 数组")
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for index, record in enumerate(raw, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"第 {index} 条产品不是对象")
        missing = sorted(field for field in REQUIRED_FIELDS if not record.get(field))
        if missing:
            raise ValueError(f"第 {index} 条产品缺少字段: {', '.join(missing)}")
        product_no = str(record["product_no"]).strip()
        if product_no in seen:
            raise ValueError(f"输入中产品编号重复: {product_no}")
        if record.get("face_price") == 99999 and record.get("completeness_status") != "pending":
            raise ValueError(f"占位面价产品必须标记 pending: {product_no}")
        seen.add(product_no)
        records.append(record)
    return records


async def import_records(records: list[dict[str, Any]], *, check_only: bool = False) -> dict:
    report = {"total": len(records), "created": 0, "updated": 0, "existing": 0, "failed": []}
    async with AsyncSessionLocal() as db:
        for record in records:
            try:
                existing = await db.scalar(
                    select(Product).where(
                        Product.product_no == record["product_no"], Product.is_deleted.is_(False)
                    )
                )
                if existing:
                    report["existing"] += 1
                    if not check_only:
                        for field in (
                            "product_name",
                            "face_price",
                            "cost_price",
                            "material",
                            "specification",
                            "colors",
                            "description",
                            "data_source",
                            "completeness_status",
                            "stock_status",
                            "status",
                        ):
                            if field in record:
                                setattr(existing, field, record.get(field))
                        await db.commit()
                        report["updated"] += 1
                    continue

                supplier = await db.scalar(
                    select(Supplier).where(
                        Supplier.supplier_name == record["supplier_name"],
                        Supplier.is_deleted.is_(False),
                    )
                )
                parent = await db.scalar(
                    select(Category).where(
                        Category.parent_id.is_(None),
                        Category.level == 1,
                        Category.category_name == record["category_parent"],
                        Category.is_deleted.is_(False),
                    )
                )
                category = None
                if parent:
                    category = await db.scalar(
                        select(Category).where(
                            Category.parent_id == parent.id,
                            Category.level == 2,
                            Category.category_name == record["category_name"],
                            Category.is_deleted.is_(False),
                        )
                    )
                series = await db.scalar(
                    select(Tag).where(
                        Tag.tag_name == record["series"],
                        Tag.tag_type == "series",
                        Tag.is_deleted.is_(False),
                    )
                )
                missing = []
                if not supplier:
                    missing.append("supplier")
                if not category:
                    missing.append("category")
                if not series:
                    missing.append("series")
                if missing:
                    raise ValueError("关联数据缺失: " + ", ".join(missing))

                brand = await db.scalar(
                    select(Brand).where(
                        Brand.brand_name == record["brand_name"], Brand.is_deleted.is_(False)
                    )
                )
                if not brand and not check_only:
                    brand = Brand(brand_name=record["brand_name"], description="圣奥试点品牌")
                    db.add(brand)
                    await db.flush()
                if check_only:
                    continue

                style = await db.scalar(
                    select(Tag).where(
                        Tag.tag_name == record.get("style"),
                        Tag.tag_type == "style",
                        Tag.is_deleted.is_(False),
                    )
                )
                if record.get("style") and not style:
                    style = Tag(tag_name=record["style"], tag_type="style")
                    db.add(style)
                    await db.flush()

                product = Product(
                    product_no=record["product_no"],
                    product_name=record["product_name"],
                    brand_id=brand.id,
                    supplier_id=supplier.id,
                    category_id=category.id,
                    face_price=record.get("face_price"),
                    cost_price=record.get("cost_price"),
                    material=record.get("material"),
                    specification=record.get("specification"),
                    colors=record.get("colors"),
                    description=record.get("description"),
                    data_source=record["data_source"],
                    completeness_status=record.get("completeness_status", "pending"),
                    stock_status=record.get("stock_status", "unknown"),
                    status=record.get("status", "draft"),
                )
                db.add(product)
                await db.flush()
                db.add(ProductTag(product_id=product.id, tag_id=series.id))
                if style:
                    db.add(ProductTag(product_id=product.id, tag_id=style.id))
                await db.commit()
                report["created"] += 1
            except Exception as exc:  # noqa: BLE001 - report partial failures per product
                await db.rollback()
                report["failed"].append(
                    {"product_no": record.get("product_no"), "reason": str(exc)}
                )
    return report


async def _main(path: Path, check_only: bool) -> None:
    records = validate_records(json.loads(path.read_text(encoding="utf-8")))
    report = await import_records(records, check_only=check_only)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入圣奥可追溯试点产品")
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--check", action="store_true", help="只执行预检，不写入")
    args = parser.parse_args()
    asyncio.run(_main(args.json_path, args.check))
