"""Approved content DNA operational Skill seed (Track B).

This script seeds four operational rows, two internal operational Skills per
approved DNA source.  Existing ``content-default`` / ``topic-basic`` rows are
left untouched for read compatibility, but are not seeded or presented as
user-selectable DNA sources.

用法::

    python -m app.scripts.seed_default_skills --check
    python -m app.scripts.seed_default_skills --apply
    python -m app.scripts.seed_default_skills --refresh --check   # 查看待刷新字段
    python -m app.scripts.seed_default_skills --refresh --apply   # 用代码模板刷新已存在的运营 Skill
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.content_skill import ContentSkill  # noqa: E402
from app.services.content_dna import OPERATIONAL_SKILLS  # noqa: E402
from app.services.content_service import PROMPT_VERSION  # noqa: E402

DEFAULT_SKILLS = [
    {
        **spec,
        "prompt_version": PROMPT_VERSION,
        "supported_platforms": ["xhs", "douyin", "moments", "seo", "other"],
    }
    for spec in OPERATIONAL_SKILLS
]


def _now() -> datetime:
    return datetime.now(UTC)


async def run(*, apply: bool, refresh: bool = False) -> int:
    created = 0
    refreshed = 0
    async with AsyncSessionLocal() as db:
        for spec in DEFAULT_SKILLS:
            existing = (
                (
                    await db.execute(
                        select(ContentSkill).where(
                            ContentSkill.code == spec["code"],
                            ContentSkill.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing is not None:
                if not refresh:
                    print(f"[skip] {spec['code']} 已存在")
                    continue
                changed = [
                    field
                    for field in (
                        "name",
                        "description",
                        "skill_type",
                        "source_dna",
                        "prompt_template",
                        "output_schema",
                        "prompt_version",
                        "supported_platforms",
                        "sort_order",
                    )
                    if getattr(existing, field) != spec[field]
                ]
                if not changed and existing.enabled:
                    print(f"[same] {spec['code']} 已是最新")
                    continue
                if not apply:
                    print(f"[plan] {spec['code']} 待刷新字段: {', '.join(changed) or 'enabled'}")
                    refreshed += 1
                    continue
                for field in (
                    "name",
                    "description",
                    "skill_type",
                    "source_dna",
                    "prompt_template",
                    "output_schema",
                    "prompt_version",
                    "supported_platforms",
                    "sort_order",
                ):
                    setattr(existing, field, spec[field])
                existing.enabled = True
                existing.update_time = _now()
                refreshed += 1
                print(f"[refresh] {spec['code']} ({', '.join(changed) or 'enabled'})")
                continue
            if not apply:
                print(f"[plan] {spec['code']} ({spec['skill_type']})")
                created += 1
                continue
            db.add(
                ContentSkill(
                    id=uuid4(),
                    code=spec["code"],
                    name=spec["name"],
                    skill_type=spec["skill_type"],
                    description=spec["description"],
                    source_dna=spec["source_dna"],
                    prompt_template=spec["prompt_template"],
                    output_schema=spec["output_schema"],
                    prompt_version=spec["prompt_version"],
                    supported_platforms=spec["supported_platforms"],
                    enabled=True,
                    sort_order=spec["sort_order"],
                    create_time=_now(),
                    update_time=_now(),
                )
            )
            created += 1
            print(f"[apply] {spec['code']} ({spec['skill_type']})")
        if apply:
            await db.commit()
    print(f"[{'APPLY' if apply else 'CHECK'}] created={created} refreshed={refreshed}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="默认内容 Skill 种子（幂等）")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="用代码中的模板刷新已存在的运营 Skill（会覆盖后台对这些内置 Skill 提示词的手动修改）",
    )
    args = parser.parse_args(argv)
    return asyncio.run(run(apply=bool(args.apply), refresh=bool(args.refresh)))


if __name__ == "__main__":
    raise SystemExit(main())
