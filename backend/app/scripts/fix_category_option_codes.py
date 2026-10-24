"""清理 ``category`` 选项里遗留的旧 UUID ``code``（一次性维护脚本）。

背景：早期版本把 category 选项的 ``code`` 设成了 ``category.id.hex``，导致
``_category_predicate``（按类目名递归匹配）永远命中不了这些选项。后续版本把
``code`` 改成类目名重新播种，于是库里同时留下两批选项：

* ``code = 类目名``（正统，可被按名匹配）；
* ``code = <32 位 UUID>``（孤儿副本，检索不可达）。

本脚本把孤儿选项安全收敛：

1. **改名**（无冲突时）：``code`` 改为 ``label``（类目名），并补齐 label 别名；
   已有别名一律**保留**，绝不被覆盖或删除。
2. **合并**（``label`` 已被同属性下另一个选项占用时）：把孤儿视为主选项的
   重复副本——先把它独有的别名/产品取值迁移到主选项（冲突时保留主选项原有行），
   再软删孤儿选项本身。不会硬删任何数据。

用法::

    python -m app.scripts.fix_category_option_codes --check
    python -m app.scripts.fix_category_option_codes --apply
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.knowledge.attributes import normalize_text  # noqa: E402
from app.models.catalog_attribute import (  # noqa: E402
    CatalogAttributeAlias,
    CatalogAttributeDefinition,
    CatalogAttributeOption,
    ProductAttributeValue,
)

_UUID_RE = re.compile(r"^[0-9a-f]{32}$")
_MAX_CODE_LEN = 64


@dataclass
class Report:
    renamed: int = 0
    merged: int = 0
    skipped: int = 0
    conflicts: list[str] = field(default_factory=list)
    aliases_moved: int = 0
    aliases_added: int = 0
    aliases_kept: int = 0
    values_moved: int = 0
    values_soft_deleted: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


async def _load_category_options(db) -> tuple[CatalogAttributeDefinition | None, list]:
    definition = (
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
    if definition is None:
        return None, []
    options = (
        (
            await db.execute(
                select(CatalogAttributeOption).where(
                    CatalogAttributeOption.attribute_id == definition.id,
                    CatalogAttributeOption.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    return definition, options


async def _canonical_for(
    db, attribute_id: UUID, code: str, exclude_id: UUID
) -> CatalogAttributeOption | None:
    return (
        (
            await db.execute(
                select(CatalogAttributeOption).where(
                    CatalogAttributeOption.attribute_id == attribute_id,
                    CatalogAttributeOption.code == code,
                    CatalogAttributeOption.is_deleted.is_(False),
                    CatalogAttributeOption.id != exclude_id,
                )
            )
        )
        .scalars()
        .first()
    )


async def _ensure_alias(db, option, alias: str, source: str) -> tuple[bool, bool]:
    """保证 option 上存在 alias；返回 (created, existed)。"""
    normalized = normalize_text(alias)
    if not normalized:
        return False, True
    row = (
        (
            await db.execute(
                select(CatalogAttributeAlias).where(
                    CatalogAttributeAlias.option_id == option.id,
                    CatalogAttributeAlias.normalized_alias == normalized,
                    CatalogAttributeAlias.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .first()
    )
    if row is not None:
        return False, True
    db.add(
        CatalogAttributeAlias(
            id=uuid4(),
            option_id=option.id,
            alias=alias,
            normalized_alias=normalized,
            source=source,
            enabled=True,
            create_time=_now(),
            update_time=_now(),
        )
    )
    return True, False


async def _move_aliases(
    db, source_option, target_option, report: Report, *, apply: bool
) -> None:
    aliases = (
        (
            await db.execute(
                select(CatalogAttributeAlias).where(
                    CatalogAttributeAlias.option_id == source_option.id,
                    CatalogAttributeAlias.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    for alias in aliases:
        normalized = normalize_text(alias.alias)
        conflict = (
            (
                await db.execute(
                    select(CatalogAttributeAlias).where(
                        CatalogAttributeAlias.option_id == target_option.id,
                        CatalogAttributeAlias.normalized_alias == normalized,
                        CatalogAttributeAlias.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .first()
        )
        if conflict is not None:
            # 主选项已有同归一化别名：孤立副本的别名不再需要
            report.aliases_kept += 1
            if apply:
                alias.is_deleted = True
                alias.deleted_at = _now()
                alias.update_time = _now()
            continue
        report.aliases_moved += 1
        if apply:
            alias.option_id = target_option.id
            alias.source = alias.source or "manual"
            alias.update_time = _now()


async def _move_values(
    db, source_option, target_option, report: Report, *, apply: bool
) -> None:
    values = (
        (
            await db.execute(
                select(ProductAttributeValue).where(
                    ProductAttributeValue.option_id == source_option.id,
                    ProductAttributeValue.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    for value in values:
        existing = (
            (
                await db.execute(
                    select(ProductAttributeValue).where(
                        ProductAttributeValue.product_id == value.product_id,
                        ProductAttributeValue.attribute_id == value.attribute_id,
                        ProductAttributeValue.option_id == target_option.id,
                        ProductAttributeValue.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            report.values_moved += 1
            if apply:
                value.option_id = target_option.id
                value.update_time = _now()
        else:
            # 主选项已有该产品该属性的取值：保留更可信的一条
            keep_existing = (
                (existing.verified and not value.verified)
                or (existing.confidence or 0) >= (value.confidence or 0)
            )
            report.values_soft_deleted += 1 if not keep_existing else 0
            if apply:
                if not keep_existing:
                    existing.note = (
                        f"merged from duplicate option {source_option.code}"
                    )
                    existing.update_time = _now()
                value.is_deleted = True
                value.deleted_at = _now()
                value.update_time = _now()


async def run(*, apply: bool) -> int:
    report = Report()
    async with AsyncSessionLocal() as db:
        definition, options = await _load_category_options(db)
        if definition is None:
            print("[check] 未定义 category 属性，无需修复")
            return 0

        for option in options:
            code = (option.code or "").strip()
            if not _UUID_RE.match(code):
                continue
            label = (option.label or "").strip()
            if not label:
                # label 丢失：保留现状，交由人工确认，绝不瞎猜
                report.skipped += 1
                report.conflicts.append(f"option {option.id}: label 为空，无法推导 code")
                continue

            target_code = label[:_MAX_CODE_LEN]
            canonical = await _canonical_for(db, definition.id, target_code, option.id)
            if canonical is None:
                # 1) 无冲突：直接改名 + 保留/补齐别名
                print(f"[plan] rename {option.id} {code[:8]}... -> {target_code}")
                report.renamed += 1
                if apply:
                    option.code = target_code
                    option.update_time = _now()
                    created, existed = await _ensure_alias(
                        db, option, label, "category_tree"
                    )
                    report.aliases_added += int(created)
                    report.aliases_kept += int(existed)
            else:
                # 2) 冲突：孤儿是主选项的重复副本，合并后软删
                print(
                    f"[plan] merge {option.id} {code[:8]}... -> {canonical.id} "
                    f"(label={label})"
                )
                report.merged += 1
                if apply:
                    await _move_aliases(db, option, canonical, report, apply=True)
                    await _move_values(db, option, canonical, report, apply=True)
                    option.is_deleted = True
                    option.deleted_at = _now()
                    option.enabled = False
                    option.update_time = _now()

        if apply:
            await db.commit()

    mode = "APPLY" if apply else "CHECK"
    print(
        f"[{mode}] renamed={report.renamed} merged={report.merged} "
        f"skipped={report.skipped} aliases_moved={report.aliases_moved} "
        f"aliases_added={report.aliases_added} aliases_kept={report.aliases_kept} "
        f"values_moved={report.values_moved} "
        f"values_soft_deleted={report.values_soft_deleted}"
    )
    for line in report.conflicts:
        print(f"[{mode}][conflict] {line}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="修复 category 选项 code（一次性）")
    parser.add_argument("--check", action="store_true", help="只读预览（默认）")
    parser.add_argument("--apply", action="store_true", help="写入数据库")
    args = parser.parse_args(argv)
    return asyncio.run(run(apply=bool(args.apply)))


if __name__ == "__main__":
    raise SystemExit(main())
