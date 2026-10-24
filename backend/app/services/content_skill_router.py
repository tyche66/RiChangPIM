"""Server-side Skill selection for the content domain.

The browser may request one of the two operational Skill codes or omit the
choice.  It cannot choose an arbitrary model or Skill.  Automatic selection
uses one bounded JSON routing call and falls back deterministically when the
router is unavailable, times out, or returns an invalid code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from sqlalchemy import select

from app.adapters.base import AIServiceAdapter
from app.models.content_skill import ContentSkill
from app.services.content_dna import (
    DEFAULT_DNA_CODE,
    LEGACY_COMPAT_CODES,
    OPERATIONAL_SKILL_CODES,
)

logger = logging.getLogger(__name__)


class SkillSelectionError(ValueError):
    """A client-selected Skill was not an enabled operational Skill."""


def _skill_type_default(skill_type: str) -> str:
    return f"{DEFAULT_DNA_CODE}-{skill_type}"


def _is_operational(skill: ContentSkill, skill_type: str) -> bool:
    return (
        skill.code in OPERATIONAL_SKILL_CODES
        and skill.skill_type == skill_type
        and skill.source_dna in {"yuc", "yanye"}
    )


async def _enabled_operational_skills(db: Any, skill_type: str) -> list[ContentSkill]:
    result = await db.execute(
        select(ContentSkill)
        .where(
            ContentSkill.is_deleted.is_(False),
            ContentSkill.enabled.is_(True),
            ContentSkill.skill_type == skill_type,
            ContentSkill.source_dna.in_(["yuc", "yanye"]),
        )
        .order_by(ContentSkill.sort_order, ContentSkill.code)
    )
    scalars = result.scalars()
    rows = scalars.all() if hasattr(scalars, "all") else list(scalars)
    return [skill for skill in rows if _is_operational(skill, skill_type)]


async def _legacy_fallback(db: Any, skill_type: str) -> ContentSkill | None:
    code = "content-default" if skill_type == "content" else "topic-basic"
    result = await db.execute(
        select(ContentSkill).where(
            ContentSkill.code == code,
            ContentSkill.is_deleted.is_(False),
            ContentSkill.enabled.is_(True),
            ContentSkill.skill_type == skill_type,
        )
    )
    skill = result.scalar_one_or_none()
    return skill if skill is not None and skill.code in LEGACY_COMPAT_CODES else None


def _parse_route_code(answer: str) -> str | None:
    text = (answer or "").strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    code = payload.get("skill_code") if isinstance(payload, dict) else None
    return code if isinstance(code, str) else None


async def _auto_route(
    skills: list[ContentSkill],
    adapter: AIServiceAdapter | None,
    *,
    skill_type: str,
    model: str | None,
    route_context: str | None = None,
    timeout_seconds: float | None = None,
) -> ContentSkill | None:
    if not adapter or len(skills) < 2:
        return None
    if timeout_seconds is None:
        from app.core.config import settings

        timeout_seconds = settings.CONTENT_AI_ROUTE_TIMEOUT
    choices = ", ".join(skill.code for skill in skills)
    prompt = (
        "你是内容 Skill 路由器，只能从给定白名单中选择一个 code。"
        "只输出 JSON，例如 {\"skill_code\":\"yuc-content\"}，不要输出其他文字。\n"
        f"skill_type={skill_type}\n可选 code={choices}\n"
        f"请求上下文={route_context or '办公场景内容'}"
    )
    try:
        try:
            response = await asyncio.wait_for(
                adapter.chat(
                    session_id=f"content_skill_route:{skill_type}",
                    message=prompt,
                    history=[],
                    stream=False,
                    temperature=0,
                    model=model,
                ),
                timeout=timeout_seconds,
            )
        except TypeError as exc:
            if "model" not in str(exc):
                raise
            response = await asyncio.wait_for(
                adapter.chat(
                    session_id=f"content_skill_route:{skill_type}",
                    message=prompt,
                    history=[],
                    stream=False,
                    temperature=0,
                ),
                timeout=timeout_seconds,
            )
        code = _parse_route_code(response.get("answer", ""))
        for skill in skills:
            if skill.code == code:
                return skill
    except Exception as exc:  # noqa: BLE001 - route failure is a safe fallback
        logger.warning("content skill route fallback error_type=%s", type(exc).__name__)
    return None


async def resolve_skill(
    db: Any,
    *,
    skill_type: str,
    requested_code: str | None,
    adapter: AIServiceAdapter | None = None,
    model: str | None = None,
    route_context: str | None = None,
) -> ContentSkill:
    """Resolve a manual or automatic operational Skill selection."""
    if requested_code:
        result = await db.execute(
            select(ContentSkill).where(
                ContentSkill.code == requested_code,
                ContentSkill.is_deleted.is_(False),
                ContentSkill.enabled.is_(True),
            )
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            raise SkillSelectionError("Skill 不存在、已停用或不属于内容 DNA 来源")
        if _is_operational(skill, skill_type):
            return skill
        raise SkillSelectionError("Skill 不存在、已停用或不属于内容 DNA 来源")

    skills = await _enabled_operational_skills(db, skill_type)
    if skills:
        routed = await _auto_route(
            skills,
            adapter,
            skill_type=skill_type,
            model=model,
            route_context=route_context,
        )
        if routed is not None:
            return routed
        default_code = _skill_type_default(skill_type)
        return next((skill for skill in skills if skill.code == default_code), skills[0])

    legacy = await _legacy_fallback(db, skill_type)
    if legacy is not None:
        return legacy
    raise SkillSelectionError("当前没有启用的内容 DNA Skill")
