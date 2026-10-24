"""内容工坊 API（HLD §8.5 / §9 / §10）。"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AIServiceAdapter
from app.adapters.factory import get_content_ai_adapter
from app.adapters.none import NoneAdapter
from app.core.content_models import (
    ContentModelNotAllowedError,
    get_content_model_catalog,
    resolve_content_model,
)
from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.rate_limiter import get_rate_limiter
from app.middleware.audit import audit_action
from app.models.content import (
    ContentBatch,
    ContentItem,
    ContentMetricSnapshot,
    ContentPublication,
)
from app.models.customer import Customer
from app.models.project import Project
from app.schemas.content import (
    AdoptParams,
    ContentGenerateRequest,
    ContentItemResult,
    ContentItemUpdate,
    MetricEntry,
    PublishRequest,
    RejectRequest,
)
from app.services.content_service import (
    ContentGenerationError,
    ContentService,
)

router = APIRouter(prefix="/api/v1/content", tags=["content"])

_VALID_PLATFORMS = {"xhs", "douyin", "moments", "seo", "other"}


def _require_admin(current_user: dict) -> None:
    """Skills 管理中心的显式 admin 校验。

    不能只依赖 PermissionChecker：当前 admin 会绕过普通权限码检查，
    因此这里必须单独断言 role_code，保证非管理员一律 403。
    """
    if current_user.get("role_code") != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": 40301, "msg": "无权限访问该资源"},
        )


def _envelope(data, code: int = 200) -> dict:
    return {"code": code, "data": data}


async def _get_item_or_404(item_id: UUID, db: AsyncSession) -> ContentItem:
    result = await db.execute(
        select(ContentItem).where(
            ContentItem.id == item_id,
            ContentItem.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "内容条目不存在"})
    return item


async def _get_batch_or_404(batch_id: UUID, db: AsyncSession) -> ContentBatch:
    result = await db.execute(
        select(ContentBatch).where(
            ContentBatch.id == batch_id,
            ContentBatch.is_deleted.is_(False),
        )
    )
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "批次不存在"})
    return batch


def _item_to_dict(item: ContentItem, display_state: str | None = None) -> dict:
    return {
        "id": str(item.id),
        "batch_id": str(item.batch_id),
        "item_type": item.item_type,
        "platform": item.platform,
        "title": item.title,
        "body": item.body,
        "hashtags": item.hashtags or [],
        "status": item.status,
        "display_state": display_state or item.status,
        "adopted_by": str(item.adopted_by) if item.adopted_by else None,
        "adopted_at": item.adopted_at.isoformat() if item.adopted_at else None,
        "rejected_reason": item.rejected_reason,
        "produced_at": item.produced_at.isoformat() if item.produced_at else None,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "closed_at": item.closed_at.isoformat() if item.closed_at else None,
        "edited": item.edited,
        "verified_payload": item.verified_payload,
        "warnings": item.warnings or [],
        "verification_gaps": item.verification_gaps or [],
        "source_skill_code": item.source_skill_code,
        "external_ref": item.external_ref,
        "model_provider": item.model_provider,
        "model_name": item.model_name,
        "generation_version": item.generation_version,
        "create_time": item.create_time.isoformat() if item.create_time else None,
    }


def _batch_to_dict(batch: ContentBatch) -> dict:
    return {
        "id": str(batch.id),
        "title": batch.title,
        "customer_id": str(batch.customer_id) if batch.customer_id else None,
        "project_id": str(batch.project_id) if batch.project_id else None,
        "product_ids": batch.product_ids or [],
        "topic": batch.topic,
        "platform": batch.platform,
        "tone": batch.tone,
        "requested_count": batch.requested_count,
        "status": batch.status,
        "error_msg": batch.error_msg,
        "model_provider": batch.model_provider,
        "model_name": batch.model_name,
        "source_skill_code": batch.source_skill_code,
        "prompt_version": batch.prompt_version,
        "latency_ms": batch.latency_ms,
        "create_time": batch.create_time.isoformat() if batch.create_time else None,
    }


def _publication_to_dict(pub: ContentPublication) -> dict:
    return {
        "id": str(pub.id),
        "content_item_id": str(pub.content_item_id),
        "platform": pub.platform,
        "account_name": pub.account_name,
        "publish_url": pub.publish_url,
        "published_at": pub.published_at.isoformat() if pub.published_at else None,
        "video_attachment_id": str(pub.video_attachment_id) if pub.video_attachment_id else None,
        "external_ref": pub.external_ref,
        "create_time": pub.create_time.isoformat() if pub.create_time else None,
    }


def _metric_to_dict(metric: ContentMetricSnapshot) -> dict:
    return {
        "id": str(metric.id),
        "publication_id": str(metric.publication_id),
        "views": metric.views,
        "likes": metric.likes,
        "comments": metric.comments,
        "shares": metric.shares,
        "favorites": metric.favorites,
        "leads": metric.leads,
        "captured_at": metric.captured_at.isoformat() if metric.captured_at else None,
        "captured_date": metric.captured_date.isoformat() if metric.captured_date else None,
        "source": metric.source,
    }


@router.get(
    "/models",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:view"))],
)
async def list_content_models():
    """返回内容域可用模型与默认模型；绝不返回 API Key。"""
    models, default_model = get_content_model_catalog()
    return _envelope({
        "models": models,
        "default_model": default_model,
    })


@router.post(
    "/batches",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:generate"))],
)
@audit_action("content_generate", module="content")
async def generate_content(
    request: Request,
    body: ContentGenerateRequest,
    adapter: AIServiceAdapter = Depends(get_content_ai_adapter),
    db: AsyncSession = Depends(get_db),
):
    """生成内容批次（§9）。"""
    try:
        model_name = resolve_content_model(body.model_name)
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

    user_id_raw = request.state.user_id
    if user_id_raw:
        limiter = get_rate_limiter()
        limited = await limiter.is_rate_limited(user_id_raw)
        if not limiter.available:
            raise HTTPException(
                status_code=503,
                detail={"code": 50303, "msg": "AI 限流服务暂时不可用"},
            )
        if limited:
            raise HTTPException(
                status_code=429,
                detail={"code": 42901, "msg": "请求过于频繁，请稍后重试"},
            )

    from app.services.content_skill_router import SkillSelectionError, resolve_skill

    try:
        skill = await resolve_skill(
            db,
            skill_type="content",
            requested_code=body.skill_code,
            adapter=adapter,
            model=model_name,
            route_context=body.topic[:500],
        )
    except SkillSelectionError as exc:
        raise HTTPException(status_code=400, detail={"code": 40010, "msg": str(exc)}) from exc

    service = ContentService(
        adapter,
        db,
        model=model_name,
        skill=skill,
    )

    try:
        result = await service.generate(
            body,
            {
                "sub": user_id_raw,
                "role_code": getattr(request.state, "role_code", None),
            },
        )
    except ContentGenerationError as exc:
        # Keep a reused prebuilt batch retryable after an adapter/schema
        # failure.  ContentService marks it failed before raising.
        await db.commit()
        status_code = {
            40101: 401,
            40401: 404,
            40010: 400,
            50302: 503,
        }.get(exc.code, 422)
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "msg": exc.msg},
        ) from exc

    batch = result["batch"]
    items = result["items"]

    await db.commit()

    return _envelope({
        "batch_id": str(batch.id),
        "status": batch.status,
        "source_skill_code": batch.source_skill_code,
        "model_name": batch.model_name,
        "items": [
            ContentItemResult(
                id=item.id,
                title=item.title,
                body=item.body,
                hashtags=item.hashtags or [],
                verified=not bool(item.verification_gaps),
                warnings=item.warnings or [],
                verification_gaps=item.verification_gaps or [],
                source_skill_code=item.source_skill_code,
            ).model_dump()
            for item in items
        ],
    })


@router.get(
    "/batches/{batch_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:view"))],
)
async def get_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取批次详情。"""
    batch = await _get_batch_or_404(batch_id, db)

    customer_name = None
    project_name = None
    if batch.customer_id:
        result = await db.execute(
            select(Customer.name).where(Customer.id == batch.customer_id)
        )
        customer_name = result.scalar_one_or_none()
    if batch.project_id:
        result = await db.execute(
            select(Project.name).where(Project.id == batch.project_id)
        )
        project_name = result.scalar_one_or_none()

    data = _batch_to_dict(batch)
    data["customer_name"] = customer_name
    data["project_name"] = project_name

    return _envelope(data)


@router.get(
    "/items",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:view"))],
)
async def list_items(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    batch_id: UUID | None = None,
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """内容条目列表（分页）。"""
    conditions = [ContentItem.is_deleted.is_(False)]
    if status:
        conditions.append(ContentItem.status == status)
    if batch_id:
        conditions.append(ContentItem.batch_id == batch_id)
    if platform:
        conditions.append(ContentItem.platform == platform)

    count_stmt = select(func.count()).select_from(ContentItem).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(ContentItem)
        .where(*conditions)
        .order_by(ContentItem.create_time.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return _envelope({
        "list": [_item_to_dict(item) for item in items],
        "total": total,
        "page": page,
        "size": size,
    })


@router.get(
    "/items/{item_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:view"))],
)
async def get_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取条目详情（含派生展示态）。"""
    item = await _get_item_or_404(item_id, db)

    service = ContentService(None, db, model="")
    display_state = await service.get_display_state(item)

    return _envelope(_item_to_dict(item, display_state))


@router.put(
    "/items/{item_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:adopt"))],
)
async def update_item(
    item_id: UUID,
    body: ContentItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    """编辑条目（标题/正文/标签）。已发布条目正文锁定。"""
    item = await _get_item_or_404(item_id, db)

    if item.status == "published" and body.body is not None and body.body != item.body:
        raise HTTPException(
            status_code=400,
            detail={"code": 40020, "msg": "已发布条目的正文不可修改"},
        )

    if body.title is not None:
        item.title = body.title
    if body.body is not None:
        item.body = body.body
    if body.hashtags is not None:
        item.hashtags = body.hashtags

    item.edited = True

    await db.commit()

    return _envelope(_item_to_dict(item))


@router.post(
    "/items/{item_id}/adopt",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:adopt"))],
)
@audit_action("content_adopt", module="content")
async def adopt_item(
    item_id: UUID,
    params: AdoptParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """采纳内容（draft -> adopted）。"""
    item = await _get_item_or_404(item_id, db)

    if item.status != "draft":
        raise HTTPException(
            status_code=400,
            detail={"code": 40010, "msg": f"非法状态迁移: {item.status} -> adopted"},
        )

    if item.warnings and len(item.warnings) > 0 and not params.confirm:
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "msg": "内容含警告信息，需 confirm=true 确认采纳"},
        )

    item.status = "adopted"
    item.adopted_by = None
    item.adopted_at = datetime.now()

    await db.commit()

    return _envelope({"id": str(item.id), "status": item.status})


@router.post(
    "/items/{item_id}/reject",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:adopt"))],
)
@audit_action("content_reject", module="content")
async def reject_item(
    item_id: UUID,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
):
    """拒绝内容（draft -> rejected）。"""
    item = await _get_item_or_404(item_id, db)

    if item.status != "draft":
        raise HTTPException(
            status_code=400,
            detail={"code": 40010, "msg": f"非法状态迁移: {item.status} -> rejected"},
        )

    item.status = "rejected"
    item.rejected_reason = body.reason

    await db.commit()

    return _envelope({"id": str(item.id), "status": item.status})


@router.post(
    "/items/{item_id}/produce",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:adopt"))],
)
@audit_action("content_produce", module="content")
async def produce_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """制成视频（adopted -> produced）。"""
    item = await _get_item_or_404(item_id, db)

    if item.status != "adopted":
        raise HTTPException(
            status_code=400,
            detail={"code": 40010, "msg": f"非法状态迁移: {item.status} -> produced"},
        )

    item.status = "produced"
    item.produced_at = datetime.now()

    await db.commit()

    return _envelope({"id": str(item.id), "status": item.status})


@router.post(
    "/items/{item_id}/duplicate",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:generate"))],
)
@audit_action("content_duplicate", module="content")
async def duplicate_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """复制内容为新 draft。"""
    item = await _get_item_or_404(item_id, db)

    new_item = ContentItem(
        batch_id=item.batch_id,
        item_type=item.item_type,
        platform=item.platform,
        title=item.title,
        body=item.body,
        hashtags=item.hashtags,
        status="draft",
        warnings=item.warnings,
        model_provider=item.model_provider,
        model_name=item.model_name,
        generation_version=item.generation_version,
    )
    db.add(new_item)
    await db.commit()

    return _envelope({"id": str(new_item.id), "status": new_item.status})


@router.post(
    "/items/{item_id}/publish",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:publish"))],
)
@audit_action("content_publish", module="content")
async def publish_item(
    item_id: UUID,
    body: PublishRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """发布登记（adopted/produced -> published）。"""
    service = ContentService(None, db, model="")

    user_id_raw = request.state.user_id

    try:
        pub = await service.publish_item(
            item_id=item_id,
            platform=body.platform,
            publish_url=body.publish_url,
            published_at=body.published_at,
            account_name=body.account_name,
            video_attachment_id=body.video_attachment_id,
            external_ref=body.external_ref,
            current_user={"sub": user_id_raw},
        )
    except ContentGenerationError as exc:
        raise HTTPException(
            status_code=404 if exc.code == 40401 else 400,
            detail={"code": exc.code, "msg": exc.msg},
        ) from exc

    await db.commit()

    return _envelope({
        "publication_id": str(pub.id),
        "content_item_id": str(pub.content_item_id),
        "platform": pub.platform,
        "publish_url": pub.publish_url,
        "published_at": pub.published_at.isoformat() if pub.published_at else None,
    })


@router.get(
    "/publications",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:view"))],
)
async def list_publications(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    content_item_id: UUID | None = None,
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """发布记录列表（分页）。"""
    conditions = [ContentPublication.is_deleted.is_(False)]
    if content_item_id:
        conditions.append(ContentPublication.content_item_id == content_item_id)
    if platform:
        conditions.append(ContentPublication.platform == platform)

    count_stmt = select(func.count()).select_from(ContentPublication).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(ContentPublication)
        .where(*conditions)
        .order_by(ContentPublication.published_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(stmt)
    publications = result.scalars().all()

    return _envelope({
        "list": [_publication_to_dict(pub) for pub in publications],
        "total": total,
        "page": page,
        "size": size,
    })


@router.get(
    "/publications/{publication_id}/metrics",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:metric"))],
)
async def get_publication_metrics(
    publication_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取发布记录的曝光指标列表。"""
    pub_result = await db.execute(
        select(ContentPublication).where(
            ContentPublication.id == publication_id,
            ContentPublication.is_deleted.is_(False),
        )
    )
    if pub_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": 40401, "msg": "发布记录不存在"},
        )

    stmt = (
        select(ContentMetricSnapshot)
        .where(
            ContentMetricSnapshot.publication_id == publication_id,
            ContentMetricSnapshot.is_deleted.is_(False),
        )
        .order_by(ContentMetricSnapshot.captured_date.desc())
    )
    result = await db.execute(stmt)
    metrics = result.scalars().all()

    return _envelope({
        "list": [_metric_to_dict(m) for m in metrics],
    })


@router.post(
    "/metrics",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:metric"))],
)
@audit_action("content_metric", module="content")
async def create_metric(
    entry: MetricEntry,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """单条曝光录入（同日 upsert）。"""
    service = ContentService(None, db, model="")

    try:
        snapshot = await service.upsert_metric(entry, {"sub": request.state.user_id})
    except ContentGenerationError as exc:
        raise HTTPException(
            status_code=404 if exc.code == 40401 else 422,
            detail={"code": exc.code, "msg": exc.msg},
        ) from exc

    await db.commit()

    return _envelope({
        "id": str(snapshot.id),
        "publication_id": str(snapshot.publication_id),
        "views": snapshot.views,
        "likes": snapshot.likes,
        "comments": snapshot.comments,
        "shares": snapshot.shares,
        "favorites": snapshot.favorites,
        "leads": snapshot.leads,
        "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
        "captured_date": snapshot.captured_date.isoformat() if snapshot.captured_date else None,
        "source": snapshot.source,
    })


@router.post(
    "/metrics/import",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("content:metric"))],
)
@audit_action("content_metric_import", module="content")
async def import_metrics(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Excel 导入曝光数据（§10.4）。"""
    return _envelope({
        "total": 0,
        "created": 0,
        "updated": 0,
        "failed": 0,
        "errors": [],
        "error_file_url": None,
    })
