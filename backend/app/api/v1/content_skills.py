"""内容 Skills 与独立选题 API（Track B）。

* Skills 管理中心（仅 ``role_code=admin``，显式校验，不依赖前端开关）；
* 独立选题模块（只展示 enabled 且 ``skill_type=topic`` 的 Skill）；
* 生成表单的「启用 Skill / 使用默认模板」开关由后端重新校验。
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AIServiceAdapter
from app.adapters.factory import get_content_ai_adapter
from app.adapters.none import NoneAdapter
from app.core.content_models import ContentModelNotAllowedError, resolve_content_model
from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.content import ContentBatch
from app.models.content_skill import ContentSkill, ContentTopicItem, ContentTopicRun
from app.services.content_dna import DNA_SOURCES, OPERATIONAL_SKILL_CODES, source_dna_label
from app.services.content_skill_router import SkillSelectionError, resolve_skill
from app.services.topic_service import (
    TopicGenerationError,
    TopicService,
    validate_topic_output_schema,
)

router = APIRouter(prefix="/api/v1/content", tags=["content"])

_VALID_PLATFORMS = {"xhs", "douyin", "moments", "seo", "other"}
_DEFAULT_PLATFORM = "xhs"


def _envelope(data, code: int = 200) -> dict:
    return {"code": code, "data": data}


def _require_admin(current_user: dict) -> None:
    """Skills 管理中心的显式 admin 校验。

    PermissionChecker 对 ``role_code == "admin"`` 会整体跳过权限码检查，
    因此这里必须单独断言 role_code：非管理员一律 403。
    """
    if current_user.get("role_code") != "admin":
        raise HTTPException(
            status_code=403, detail={"code": 40301, "msg": "无权限访问该资源"}
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_topic_skill_schema(output_schema: dict[str, object] | None) -> None:
    """Reject topic schemas that cannot populate ContentTopicItem columns."""
    if output_schema is None:
        return
    errors = validate_topic_output_schema(output_schema)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "code": 40001,
                "msg": f"Topic Skill Schema 不符合选题字段约定: {errors[:3]}",
            },
        )


def _resolve_topic_platform(
    item: ContentTopicItem,
    run: ContentTopicRun | None,
    skill: ContentSkill | None,
) -> str:
    """Resolve the non-null ContentBatch platform at adoption time.

    Explicit AI suggestion wins, then the run selection, then the Skill's
    declared platform order.  The fixed default keeps old/custom Skills with
    no platform declaration compatible with the non-null batch column.
    """
    candidates = [item.suggested_platform, run.platform if run else None]
    if skill is not None:
        candidates.extend(skill.supported_platforms or [])
    candidates.append(_DEFAULT_PLATFORM)
    for candidate in candidates:
        if isinstance(candidate, str) and candidate in _VALID_PLATFORMS:
            return candidate
    return _DEFAULT_PLATFORM


def _skill_to_dict(skill: ContentSkill) -> dict:
    return {
        "id": str(skill.id),
        "code": skill.code,
        "name": skill.name,
        "skill_type": skill.skill_type,
        "description": skill.description,
        "source_dna": skill.source_dna,
        "source_dna_label": source_dna_label(skill.source_dna),
        "selectable": bool(skill.enabled and skill.code in OPERATIONAL_SKILL_CODES),
        "prompt_template": skill.prompt_template,
        "output_schema": skill.output_schema,
        "prompt_version": skill.prompt_version,
        "supported_platforms": skill.supported_platforms or [],
        "enabled": bool(skill.enabled),
        "sort_order": skill.sort_order,
        "create_time": skill.create_time.isoformat() if skill.create_time else None,
        "update_time": skill.update_time.isoformat() if skill.update_time else None,
    }


def _topic_run_to_dict(run: ContentTopicRun, items: list[ContentTopicItem] | None = None) -> dict:
    return {
        "id": str(run.id),
        "skill_id": str(run.skill_id),
        "skill_code": run.skill_code,
        "topic": run.topic,
        "platform": run.platform,
        "tone": run.tone,
        "product_ids": run.product_ids or [],
        "requested_count": run.requested_count,
        "status": run.status,
        "error_msg": run.error_msg,
        "model_provider": run.model_provider,
        "model_name": run.model_name,
        "prompt_version": run.prompt_version,
        "latency_ms": run.latency_ms,
        "create_time": run.create_time.isoformat() if run.create_time else None,
        "items": [_topic_item_to_dict(i) for i in (items or [])],
    }


def _topic_item_to_dict(item: ContentTopicItem) -> dict:
    return {
        "id": str(item.id),
        "run_id": str(item.run_id),
        "title": item.title,
        "angle": item.angle,
        "audience": item.audience,
        "reason": item.reason,
        "suggested_platform": item.suggested_platform,
        "related_product_ids": item.related_product_ids or [],
        "pillar_code": item.pillar_code,
        "verification_gaps": item.verification_gaps or [],
        "source_skill_code": item.source_skill_code,
        "status": item.status,
        "adopted_by": str(item.adopted_by) if item.adopted_by else None,
        "adopted_at": item.adopted_at.isoformat() if item.adopted_at else None,
        "rejected_reason": item.rejected_reason,
        "content_batch_id": str(item.content_batch_id) if item.content_batch_id else None,
        "create_time": item.create_time.isoformat() if item.create_time else None,
    }


def _topic_context(item: ContentTopicItem) -> str:
    """把选题的标题/角度/人群拼成内容工坊的生成主题。"""
    parts = [item.title]
    if item.angle:
        parts.append(f"角度：{item.angle}")
    if item.audience:
        parts.append(f"目标人群：{item.audience}")
    if item.reason:
        parts.append(f"选题理由：{item.reason}")
    return "；".join(parts)


async def _get_enabled_skill(skill_code: str, db: AsyncSession) -> ContentSkill:
    """按 code 取启用中的 Skill；停用/不存在一律拒绝（不信任前端开关）。"""
    result = await db.execute(
        select(ContentSkill).where(
            ContentSkill.code == skill_code,
            ContentSkill.is_deleted.is_(False),
        )
    )
    skill = result.scalar_one_or_none()
    if skill is None or not skill.enabled:
        raise HTTPException(
            status_code=400, detail={"code": 40010, "msg": "Skill 不存在或已停用"}
        )
    return skill


# ---------------------------------------------------------------------------
# Skills 选用（内容生成 / 选题共用）
# ---------------------------------------------------------------------------


@router.get(
    "/skills",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:view"))],
)
async def list_skills(
    skill_type: str | None = None,
    enabled_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """列出 Skill。默认只返回启用中的；``skill_type`` 可传 topic/content。"""
    conditions = [ContentSkill.is_deleted.is_(False)]
    if enabled_only:
        conditions.append(ContentSkill.enabled.is_(True))
    if skill_type:
        conditions.append(ContentSkill.skill_type == skill_type)
    # User-facing lists expose the two approved DNA sources only. Legacy rows
    # remain queryable by admin/internal compatibility paths.
    conditions.append(ContentSkill.source_dna.in_(list(DNA_SOURCES)))
    result = await db.execute(
        select(ContentSkill).where(*conditions).order_by(ContentSkill.sort_order, ContentSkill.code)
    )
    return _envelope([_skill_to_dict(s) for s in result.scalars().all()])


# ---------------------------------------------------------------------------
# Skills 管理中心（仅 admin）
# ---------------------------------------------------------------------------


@router.get(
    "/skills/manage",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:manage"))],
)
async def list_skills_for_manage(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """管理中心列表：包含已停用的 Skill（仅 admin）。"""
    _require_admin({"role_code": getattr(request.state, "role_code", None)})
    result = await db.execute(
        select(ContentSkill)
        .where(ContentSkill.is_deleted.is_(False))
        .order_by(ContentSkill.sort_order, ContentSkill.code)
    )
    return _envelope([_skill_to_dict(s) for s in result.scalars().all()])


class SkillCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    skill_type: str = Field(default="content", pattern="^(topic|content)$")
    description: str | None = None
    prompt_template: str | None = None
    output_schema: dict[str, object] | None = None
    prompt_version: str = Field(default="v1", max_length=16)
    supported_platforms: list[str] = Field(default_factory=list)
    enabled: bool = True
    sort_order: int = 0


class SkillUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    prompt_template: str | None = None
    output_schema: dict[str, object] | None = None
    prompt_version: str | None = Field(default=None, max_length=16)
    supported_platforms: list[str] | None = None
    enabled: bool | None = None
    sort_order: int | None = None


class SkillToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


@router.post(
    "/skills/manage",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:manage"))],
)
@audit_action("content_skill_create", module="content")
async def create_skill(
    request: Request,
    payload: SkillCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """新增 Skill（仅 admin；写操作接入审计）。"""
    _require_admin({"role_code": getattr(request.state, "role_code", None)})
    if payload.skill_type == "topic":
        _validate_topic_skill_schema(payload.output_schema)
    existing = await db.execute(
        select(ContentSkill).where(
            ContentSkill.code == payload.code, ContentSkill.is_deleted.is_(False)
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail={"code": 40010, "msg": "Skill code 已存在"})

    user_id = getattr(request.state, "user_id", None)
    skill = ContentSkill(
        id=uuid4(),
        code=payload.code,
        name=payload.name,
        skill_type=payload.skill_type,
        description=payload.description,
        prompt_template=payload.prompt_template,
        output_schema=payload.output_schema,
        prompt_version=payload.prompt_version,
        supported_platforms=payload.supported_platforms,
        enabled=payload.enabled,
        sort_order=payload.sort_order,
        create_time=_now(),
        update_time=_now(),
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _envelope(_skill_to_dict(skill))


@router.put(
    "/skills/manage/{skill_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:manage"))],
)
@audit_action("content_skill_update", module="content")
async def update_skill(
    request: Request,
    skill_id: UUID,
    payload: SkillUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """编辑 Skill（仅 admin；写操作接入审计）。"""
    _require_admin({"role_code": getattr(request.state, "role_code", None)})
    result = await db.execute(
        select(ContentSkill).where(
            ContentSkill.id == skill_id, ContentSkill.is_deleted.is_(False)
        )
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "Skill 不存在"})

    if skill.skill_type == "topic" and payload.output_schema is not None:
        _validate_topic_skill_schema(payload.output_schema)

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(skill, key, value)
    skill.update_time = _now()
    skill.updated_by = getattr(request.state, "user_id", None)
    await db.commit()
    await db.refresh(skill)
    return _envelope(_skill_to_dict(skill))


@router.post(
    "/skills/manage/{skill_id}/toggle",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:manage"))],
)
@audit_action("content_skill_toggle", module="content")
async def toggle_skill(
    request: Request,
    skill_id: UUID,
    payload: SkillToggleRequest,
    db: AsyncSession = Depends(get_db),
):
    """启用/停用 Skill（仅 admin；写操作接入审计）。"""
    _require_admin({"role_code": getattr(request.state, "role_code", None)})
    result = await db.execute(
        select(ContentSkill).where(
            ContentSkill.id == skill_id, ContentSkill.is_deleted.is_(False)
        )
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "Skill 不存在"})

    skill.enabled = payload.enabled
    skill.update_time = _now()
    skill.updated_by = getattr(request.state, "user_id", None)
    await db.commit()
    await db.refresh(skill)
    return _envelope(_skill_to_dict(skill))


@router.delete(
    "/skills/manage/{skill_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:manage"))],
)
@audit_action("content_skill_delete", module="content")
async def delete_skill(
    request: Request,
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """软删除 Skill（仅 admin；写操作接入审计）。"""
    _require_admin({"role_code": getattr(request.state, "role_code", None)})
    result = await db.execute(
        select(ContentSkill).where(
            ContentSkill.id == skill_id, ContentSkill.is_deleted.is_(False)
        )
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "Skill 不存在"})

    skill.is_deleted = True
    skill.deleted_at = _now()
    skill.enabled = False
    skill.update_time = _now()
    skill.updated_by = getattr(request.state, "user_id", None)
    await db.commit()
    return _envelope({"id": str(skill.id), "deleted": True})


# ---------------------------------------------------------------------------
# 独立选题
# ---------------------------------------------------------------------------


class TopicRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None means server-side auto routing across the enabled two DNA sources.
    skill_code: str | None = Field(default=None, min_length=1, max_length=64)
    # 未传时使用 CONTENT_AI_CHAT_MODEL；显式值必须命中服务端白名单。
    model_name: str | None = Field(default=None, max_length=64)
    topic: str = Field(min_length=1, max_length=2000)
    platform: str | None = Field(
        default=None,
        pattern="^(xhs|douyin|moments|seo|other)$",
    )
    tone: str | None = Field(default=None, max_length=32)
    product_ids: list[UUID] = Field(default_factory=list, max_length=10)
    requested_count: int = Field(default=3, ge=1, le=10)


@router.post(
    "/topics/runs",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:generate"))],
)
@audit_action("content_topic_run_create", module="content")
async def create_topic_run(
    request: Request,
    payload: TopicRunCreateRequest,
    adapter: AIServiceAdapter = Depends(get_content_ai_adapter),
    db: AsyncSession = Depends(get_db),
):
    """创建独立选题运行并**真实生成**选题条目。

    生成链路：Skill 提示词 -> AI -> output_schema 校验 -> 合规检查 ->
    落库 ContentTopicItem；run 状态推进到 done / failed，失败写 error_msg。
    """
    try:
        model_name = resolve_content_model(payload.model_name)
    except ContentModelNotAllowedError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": 40010, "msg": str(exc)},
        ) from exc

    if adapter is None or isinstance(adapter, NoneAdapter):
        raise HTTPException(
            status_code=503,
            detail={"code": 50302, "msg": "AI 能力中心未配置"},
        )

    try:
        skill = await resolve_skill(
            db,
            skill_type="topic",
            requested_code=payload.skill_code,
            adapter=adapter,
            model=model_name,
            route_context=payload.topic[:500],
        )
    except SkillSelectionError as exc:
        raise HTTPException(status_code=400, detail={"code": 40010, "msg": str(exc)}) from exc
    _validate_topic_skill_schema(skill.output_schema)

    user_id = getattr(request.state, "user_id", None)
    run = ContentTopicRun(
        id=uuid4(),
        skill_id=skill.id,
        skill_code=skill.code,
        topic=payload.topic,
        platform=payload.platform,
        tone=payload.tone,
        product_ids=[str(pid) for pid in payload.product_ids],
        requested_count=payload.requested_count,
        status="running",
        prompt_version=skill.prompt_version,
        create_time=_now(),
        update_time=_now(),
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(run)
    await db.flush()

    service = TopicService(adapter, db, model=model_name)
    try:
        items = await service.generate(run, skill, {"sub": user_id})
    except TopicGenerationError as exc:
        # 失败原因已经写进 run.error_msg；这里再落库一次保证事务提交
        await db.commit()
        raise HTTPException(
            status_code=503 if exc.code == 50302 else 422,
            detail={"code": exc.code, "msg": exc.msg},
        ) from exc

    await db.commit()
    await db.refresh(run)
    return _envelope(_topic_run_to_dict(run, list(items)))


@router.get(
    "/topics/runs",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:view"))],
)
async def list_topic_runs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContentTopicRun)
        .where(ContentTopicRun.is_deleted.is_(False))
        .order_by(ContentTopicRun.create_time.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    runs = result.scalars().all()
    count_result = await db.execute(
        select(ContentTopicRun.id).where(ContentTopicRun.is_deleted.is_(False))
    )
    total = len(count_result.scalars().all())
    return _envelope(
        {
            "list": [_topic_run_to_dict(r) for r in runs],
            "total": total,
            "page": page,
            "size": size,
        }
    )


@router.get(
    "/topics/runs/{run_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:view"))],
)
async def get_topic_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContentTopicRun).where(
            ContentTopicRun.id == run_id, ContentTopicRun.is_deleted.is_(False)
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "选题运行不存在"})
    items_result = await db.execute(
        select(ContentTopicItem).where(
            ContentTopicItem.run_id == run_id, ContentTopicItem.is_deleted.is_(False)
        )
    )
    return _envelope(_topic_run_to_dict(run, list(items_result.scalars().all())))


class TopicItemStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rejected_reason: str | None = Field(default=None, max_length=255)


@router.post(
    "/topics/items/{item_id}/adopt",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:adopt"))],
)
@audit_action("content_topic_item_adopt", module="content")
async def adopt_topic_item(request: Request, item_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContentTopicItem).where(
            ContentTopicItem.id == item_id, ContentTopicItem.is_deleted.is_(False)
        ).with_for_update(of=ContentTopicItem)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "选题条目不存在"})
    if item.status != "draft":
        raise HTTPException(status_code=400, detail={"code": 40010, "msg": "仅草稿状态可采纳"})
    item.status = "adopted"
    item.adopted_by = getattr(request.state, "user_id", None)
    item.adopted_at = _now()

    # 采纳即预建一个内容批次：选题的标题/角度/人群/产品会随批次一起进工坊，
    # 前端拿到 content_batch_id 就能带着 topic_id 跳转到内容工坊并预填生成表单。
    run_result = await db.execute(
        select(ContentTopicRun).where(
            ContentTopicRun.id == item.run_id,
            ContentTopicRun.is_deleted.is_(False),
        )
    )
    run = run_result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "选题运行不存在"})
    skill_result = await db.execute(
        select(ContentSkill).where(
            ContentSkill.code == item.source_skill_code,
            ContentSkill.is_deleted.is_(False),
        )
    )
    skill = skill_result.scalar_one_or_none()
    batch = ContentBatch(
        id=uuid4(),
        title=f"选题：{item.title}"[:255],
        topic=_topic_context(item),
        platform=_resolve_topic_platform(item, run, skill),
        tone=run.tone if run else None,
        product_ids=list(item.related_product_ids or []),
        source_skill_code=(
            item.source_skill_code.replace("-topic", "-content")
            if item.source_skill_code
            else None
        ),
        requested_count=3,
        status="pending",
        prompt_version="v1",
        create_time=_now(),
        update_time=_now(),
        created_by=item.adopted_by,
        updated_by=item.adopted_by,
    )
    db.add(batch)
    await db.flush()
    item.content_batch_id = batch.id
    item.update_time = _now()
    await db.commit()
    await db.refresh(item)
    payload = _topic_item_to_dict(item)
    payload["content_batch_id"] = str(batch.id)
    return _envelope(payload)


@router.get(
    "/topics/items/{item_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:view"))],
)
async def get_topic_item(item_id: UUID, db: AsyncSession = Depends(get_db)):
    """选题条目详情：内容工坊用 ``?topic_id=`` 读取它来预填生成表单。"""
    result = await db.execute(
        select(ContentTopicItem).where(
            ContentTopicItem.id == item_id,
            ContentTopicItem.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "选题条目不存在"})
    run_result = await db.execute(
        select(ContentTopicRun).where(
            ContentTopicRun.id == item.run_id,
            ContentTopicRun.is_deleted.is_(False),
        )
    )
    run = run_result.scalar_one_or_none()
    data = _topic_item_to_dict(item)
    batch = None
    if item.content_batch_id is not None:
        batch_result = await db.execute(
            select(ContentBatch).where(
                ContentBatch.id == item.content_batch_id,
                ContentBatch.is_deleted.is_(False),
            )
        )
        batch = batch_result.scalar_one_or_none()
    data["topic_context"] = _topic_context(item)
    data["platform"] = batch.platform if batch is not None else None
    data["skill_code"] = run.skill_code if run else None
    data["run_topic"] = run.topic if run else None
    return _envelope(data)


@router.post(
    "/topics/items/{item_id}/reject",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:adopt"))],
)
@audit_action("content_topic_item_reject", module="content")
async def reject_topic_item(
    request: Request,
    item_id: UUID,
    payload: TopicItemStatusRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContentTopicItem).where(
            ContentTopicItem.id == item_id, ContentTopicItem.is_deleted.is_(False)
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "选题条目不存在"})
    if item.status == "used":
        raise HTTPException(status_code=400, detail={"code": 40010, "msg": "已使用的选题不可驳回"})
    item.status = "rejected"
    item.rejected_reason = payload.rejected_reason if payload else None
    await db.commit()
    await db.refresh(item)
    return _envelope(_topic_item_to_dict(item))
