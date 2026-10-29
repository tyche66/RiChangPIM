"""按 ``backup_id`` 恢复一次「覆盖导入」之前的产品字段与图片绑定。

用法::

    python -m app.scripts.restore_import_backup --list
    python -m app.scripts.restore_import_backup <backup_id> --dry-run
    python -m app.scripts.restore_import_backup <backup_id>

只恢复快照里记录的产品（覆盖模式命中的那些）。产品 id 不变，因此方案、报价、
分享页的引用不需要跟着改；图片按原附件 id 与顺序重建，附件本身不会被删。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.product import Product, ProductImage
from app.services.product_import_backup import backup_root, load_backup

_UUID_FIELDS = {"brand_id", "supplier_id", "category_id"}


def _list_backups() -> None:
    root = backup_root()
    if not root.is_dir():
        print(f"没有快照目录：{root}")
        return
    files = sorted(root.glob("*.json"))
    if not files:
        print(f"{root} 下没有快照")
        return
    for path in files:
        print(path.stem)


async def _restore(backup_id: str, *, dry_run: bool) -> int:
    payload = load_backup(backup_id)
    products = payload.get("products") or []
    print(
        f"快照 {backup_id}（mode={payload.get('mode')}）："
        f"{len(products)} 个产品{'，演练模式' if dry_run else ''}"
    )

    restored = 0
    async with AsyncSessionLocal() as db:
        try:
            for record in products:
                product = (
                    await db.execute(
                        select(Product).where(Product.id == UUID(record["product_id"]))
                    )
                ).scalar_one_or_none()
                if product is None:
                    print(f"  跳过 {record.get('product_no')}：产品已不存在")
                    continue

                for field, value in (record.get("fields") or {}).items():
                    if field in _UUID_FIELDS and value:
                        value = UUID(value)
                    setattr(product, field, value)

                current = (
                    await db.execute(
                        select(ProductImage).where(
                            ProductImage.product_id == product.id,
                            ProductImage.is_deleted.is_(False),
                        )
                    )
                ).scalars().all()
                for image in current:
                    image.is_deleted = True
                for index, attachment_id in enumerate(record.get("image_attachment_ids") or []):
                    db.add(
                        ProductImage(
                            product_id=product.id,
                            attachment_id=UUID(attachment_id),
                            sort=index,
                            is_cover=index == 0,
                        )
                    )
                restored += 1

            if dry_run:
                await db.rollback()
            else:
                await db.commit()
        except Exception:
            await db.rollback()
            raise

    print(f"完成：{restored} 个产品{'（未提交）' if dry_run else ' 已恢复'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="恢复产品覆盖导入前的快照")
    parser.add_argument("backup_id", nargs="?", help="快照 id（不含 .json）")
    parser.add_argument("--list", action="store_true", help="列出可用快照")
    parser.add_argument("--dry-run", action="store_true", help="只演练，不提交")
    args = parser.parse_args()

    if args.list or not args.backup_id:
        _list_backups()
        return 0

    return asyncio.run(_restore(args.backup_id, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
