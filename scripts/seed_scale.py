#!/usr/bin/env python3
"""V1.2 性能规模与并发基线 — 合成数据生成器。

按 docs/v1.2-plan.md §5.6 在一个 *独立的* PG16 数据库中生成可重复的
1x / 10x / 100x 合成产品数据。所有合成产品都显式标记 ``is_synthetic``
前缀（产品编号以 ``SYN-`` 开头），避免与试点 13 条铭达真实数据混淆。

要求:
- 默认指向 ``TEST_DATABASE_URL`` 或 ``SEED_DATABASE_URL``，不得写入生产 DATABASE_URL
- 所有合成行有 ``is_synthetic`` 标记（no_image/no_manual 等任意 flag）
- 1x = 13 行（同试点规模），10x = 1,500 行，100x = 100,000 行
- 数据必须真实占位，不影响生产 (不挂载生产卷)

用法:
    TEST_DATABASE_URL=postgresql+asyncpg://pim:pwd@localhost:5432/ai_pim_seed \
        scripts/seed_scale.py --scale 1x
    ... --scale 10x
    ... --scale 100x
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Hard guard: refuse to run without an explicit SEED DSN target.
_ALLOWED_DB_NAME_MARKERS = ("seed", "test", "scale", "synthetic")


def _resolve_seed_dsn() -> str:
    dsn = os.environ.get("SEED_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL") or ""
    if not dsn:
        raise SystemExit(
            "SEED_DATABASE_URL (or TEST_DATABASE_URL) is required; "
            "seed MUST run against an isolated database, never prod."
        )
    lower = dsn.lower()
    if not any(m in lower for m in _ALLOWED_DB_NAME_MARKERS):
        raise SystemExit(
            f"refusing to seed against {dsn!r}: DB name lacks any of "
            f"{_ALLOWED_DB_NAME_MARKERS} marker; refusing to protect prod."
        )
    return dsn


_SCALE_TABLE = {
    "1x": 13,
    "10x": 1_500,
    "100x": 100_000,
}


async def _seed(dsn: str, count: int, dry_run: bool) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Importing here so the script can run with the venv that has the app deps.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from app.models.product import (  # type: ignore  # noqa: E402
        Brand,
        Category,
        Product,
        Supplier,
    )

    engine = create_async_engine(dsn, echo=False)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    base_brand = "SYN-Brand"
    base_supplier = "SYN-Supplier"
    base_category_name = "SYN-Category"

    print(f"seeding {count} synthetic products into {dsn.split('@')[-1]}")
    if dry_run:
        print("dry-run: skipping actual writes")
        return

    async with sessionmaker() as session:
        # Reuse or create brand/supplier/category to keep schema clean.
        from sqlalchemy import select

        brand = (await session.execute(select(Brand).where(Brand.brand_name == base_brand))).scalar_one_or_none()
        if brand is None:
            brand = Brand(brand_name=base_brand)
            session.add(brand)
            await session.flush()
        supplier = (await session.execute(select(Supplier).where(Supplier.supplier_name == base_supplier))).scalar_one_or_none()
        if supplier is None:
            supplier = Supplier(supplier_name=base_supplier)
            session.add(supplier)
            await session.flush()
        category = (await session.execute(select(Category).where(Category.category_name == base_category_name))).scalar_one_or_none()
        if category is None:
            category = Category(level=1, category_name=base_category_name, sort=0)
            session.add(category)
            await session.flush()

        now = datetime.now(timezone.utc)
        # Total batch time on 100k: ~30s on a laptop with bulk items.
        BATCH = 1000
        for i in range(count):
            product_no = f"SYN-{count}-{i:08d}"
            product = Product(
                product_no=product_no,
                product_name=f"合成产品 {i}",
                brand_id=brand.id,
                supplier_id=supplier.id,
                category_id=category.id,
                face_price=99999.0,  # labeled V1.2 : 待核价 placeholder, NOT a real price
                stock_status="unknown",
                status="draft",
                description=None,
                specification=f"测试规格 {i}",
                data_source="synthetic-seed-scale",
                completeness_status="pending",
            )
            session.add(product)
            if (i + 1) % BATCH == 0:
                await session.commit()
                print(f"  committed batch {(i + 1) // BATCH} ({i + 1}/{count})")
        await session.commit()
    await engine.dispose()
    print(f"done: {count} synthetic products seeded")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", choices=sorted(_SCALE_TABLE.keys()), required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dsn = _resolve_seed_dsn()
    count = _SCALE_TABLE[args.scale]
    asyncio.run(_seed(dsn, count, args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
