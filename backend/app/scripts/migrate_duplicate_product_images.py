"""Migrate the safe product-image subset of the 2026-10-29 duplicate audit.

This script deliberately does not merge products, migrate scene images, change
product status, copy tags, or retire the P- source products. It only makes the
active ``product_image`` links of each target point at the audited source
product's active product-image attachments.

The default mode is a read-only plan. A write requires both ``--apply`` and
the exact confirmation string below. The operation is one database transaction
and is idempotent: existing desired links are reused, obsolete target links
are soft-deleted, and missing desired links are inserted.

Examples::

    python -m app.scripts.migrate_duplicate_product_images
    python -m app.scripts.migrate_duplicate_product_images \
        --apply --confirm MIGRATE_PRODUCT_IMAGES_20261029
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import AsyncSessionLocal
from app.models.product import Product, ProductImage

CONFIRMATION = "MIGRATE_PRODUCT_IMAGES_20261029"
EXPECTED_PAIR_COUNT = 240


class MigrationSafetyError(RuntimeError):
    """The audited preconditions no longer match the live database."""


@dataclass(frozen=True)
class Pair:
    index: int
    source_id: UUID
    target_id: UUID
    source_no: str
    target_no: str
    product_name: str


def default_report_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "audit"
        / "20261029_duplicate_products"
        / "pairs_minimal.csv"
    )


def load_pairs(path: Path) -> list[Pair]:
    """Load and validate the exact audit pairing file before touching the DB."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != EXPECTED_PAIR_COUNT:
        raise MigrationSafetyError(
            f"expected {EXPECTED_PAIR_COUNT} audited pairs, found {len(rows)} in {path}"
        )

    pairs: list[Pair] = []
    seen_sources: set[UUID] = set()
    seen_targets: set[UUID] = set()
    seen_numbers: set[tuple[str, str]] = set()
    for expected_index, row in enumerate(rows, start=1):
        try:
            pair = Pair(
                index=int(row["pair_index"]),
                source_id=UUID(row["source_product_id"]),
                target_id=UUID(row["target_product_id"]),
                source_no=row["source_product_no"].strip(),
                target_no=row["target_product_no"].strip(),
                product_name=row["product_name"].strip(),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MigrationSafetyError(f"invalid pair row {expected_index}: {row}") from exc

        if pair.index != expected_index:
            raise MigrationSafetyError(
                f"pair_index is not contiguous at row {expected_index}: {pair.index}"
            )
        if not pair.source_no.casefold() == f"p-{pair.target_no}".casefold():
            raise MigrationSafetyError(
                f"pair {pair.index} violates the P- invariant: "
                f"{pair.source_no!r} -> {pair.target_no!r}"
            )
        if not pair.product_name:
            raise MigrationSafetyError(f"pair {pair.index} has an empty product name")
        if pair.source_id in seen_sources or pair.target_id in seen_targets:
            raise MigrationSafetyError(f"pair {pair.index} reuses a product id")
        number_key = (pair.source_no.casefold(), pair.target_no.casefold())
        if number_key in seen_numbers:
            raise MigrationSafetyError(f"pair {pair.index} reuses a product-number pair")

        seen_sources.add(pair.source_id)
        seen_targets.add(pair.target_id)
        seen_numbers.add(number_key)
        pairs.append(pair)
    return pairs


def _image_sort_key(image: ProductImage) -> tuple[int, datetime, str]:
    return (image.sort or 0, image.create_time, str(image.id))


async def _active_images(db, product_id: UUID) -> list[ProductImage]:
    result = await db.execute(
        select(ProductImage)
        .options(joinedload(ProductImage.attachment))
        .where(ProductImage.product_id == product_id, ProductImage.is_deleted.is_(False))
        .order_by(ProductImage.sort, ProductImage.create_time, ProductImage.id)
    )
    return list(result.scalars().unique().all())


async def _product(db, product_id: UUID) -> Product | None:
    return await db.scalar(select(Product).where(Product.id == product_id))


async def build_plan(db, pairs: list[Pair], *, apply: bool) -> dict[str, Any]:
    """Validate every pair and optionally apply only product-image changes."""
    summary: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "pair_count": len(pairs),
        "products_checked": 0,
        "products_changed": 0,
        "source_image_links": 0,
        "target_image_links_before": 0,
        "links_to_add": 0,
        "links_to_keep": 0,
        "links_to_soft_delete": 0,
        "target_image_links_after": 0,
        "scene_links_changed": 0,
        "products_retired": 0,
        "errors": [],
    }

    for pair in pairs:
        source = await _product(db, pair.source_id)
        target = await _product(db, pair.target_id)
        if source is None or target is None:
            raise MigrationSafetyError(f"pair {pair.index}: source or target product is missing")
        if source.is_deleted or target.is_deleted:
            raise MigrationSafetyError(f"pair {pair.index}: source or target product is deleted")
        if source.product_no != pair.source_no or target.product_no != pair.target_no:
            raise MigrationSafetyError(
                f"pair {pair.index}: product number drift; live values are "
                f"{source.product_no!r} -> {target.product_no!r}"
            )
        if source.product_name != pair.product_name or target.product_name != pair.product_name:
            raise MigrationSafetyError(f"pair {pair.index}: product name drift")

        source_images = await _active_images(db, source.id)
        target_images = await _active_images(db, target.id)
        if not source_images:
            raise MigrationSafetyError(f"pair {pair.index}: source has no active product images")
        if sum(1 for image in source_images if image.is_cover) != 1:
            raise MigrationSafetyError(
                f"pair {pair.index}: source must have exactly one active cover image"
            )
        for image in source_images:
            if image.attachment is None or image.attachment.is_deleted:
                raise MigrationSafetyError(
                    f"pair {pair.index}: source attachment is missing or deleted"
                )
            if image.attachment.file_type != "image":
                raise MigrationSafetyError(
                    f"pair {pair.index}: source attachment is not an image"
                )

        desired = sorted(source_images, key=_image_sort_key)
        existing_by_attachment: dict[UUID, list[ProductImage]] = {}
        for image in target_images:
            existing_by_attachment.setdefault(image.attachment_id, []).append(image)

        keep_ids: set[UUID] = set()
        add_count = 0
        for index, source_image in enumerate(desired):
            candidates = existing_by_attachment.get(source_image.attachment_id, [])
            existing = candidates.pop(0) if candidates else None
            if existing is None:
                add_count += 1
                if apply:
                    db.add(
                        ProductImage(
                            product_id=target.id,
                            attachment_id=source_image.attachment_id,
                            sort=index,
                            is_cover=source_image.is_cover,
                        )
                    )
            else:
                keep_ids.add(existing.id)
                if apply:
                    existing.sort = index
                    existing.is_cover = source_image.is_cover

        obsolete = [image for image in target_images if image.id not in keep_ids]
        if apply:
            deleted_at = datetime.now(UTC)
            for image in obsolete:
                image.is_deleted = True
                image.deleted_at = deleted_at

        summary["products_checked"] += 1
        summary["source_image_links"] += len(desired)
        summary["target_image_links_before"] += len(target_images)
        summary["links_to_add"] += add_count
        summary["links_to_keep"] += len(keep_ids)
        summary["links_to_soft_delete"] += len(obsolete)
        summary["target_image_links_after"] += len(desired)
        if add_count or obsolete:
            summary["products_changed"] += 1

    if apply:
        await db.flush()
    return summary


async def run(report_path: Path, *, apply: bool) -> dict[str, Any]:
    pairs = load_pairs(report_path)
    async with AsyncSessionLocal() as db:
        try:
            summary = await build_plan(db, pairs, apply=apply)
            if apply:
                await db.commit()
            else:
                await db.rollback()
            summary["report"] = str(report_path)
            summary["committed"] = apply
            return summary
        except Exception:
            await db.rollback()
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=default_report_path())
    parser.add_argument("--apply", action="store_true", help="commit the product-image links")
    parser.add_argument("--confirm", help=f"required with --apply: {CONFIRMATION}")
    parser.add_argument("--output", type=Path, help="also write the JSON result to this path")
    args = parser.parse_args()

    if args.apply and args.confirm != CONFIRMATION:
        parser.error(f"--apply requires --confirm {CONFIRMATION}")
    if not args.report.is_file():
        parser.error(f"audit report not found: {args.report}")

    try:
        result = asyncio.run(run(args.report, apply=args.apply))
    except (MigrationSafetyError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    result = {"ok": True, **result}
    rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
