"""向量索引管理 API（v1.9.9）。

对应夜间调度服务 app/services/knowledge_index_scheduler.py：

  GET  /api/v1/knowledge-index/settings   读取配置 + 调度状态
  PUT  /api/v1/knowledge-index/settings   更新配置（审计；密钥不在此表）
  GET  /api/v1/knowledge-index/status     状态卡：心跳/下次调度/队列/隔离
  GET  /api/v1/knowledge-index/runs       最近运行报告（默认 30 条）
  POST /api/v1/knowledge-index/run-now    手动运行（后端强制 ≤200 产品）
  POST /api/v1/knowledge-index/jobs/reset 授权的失败任务重置（审计）

安全约定：本路由的任何响应都不包含密钥；配置表本身不存凭据；运行报告的
error_summary 在调度服务写入前已统一脱敏。权限：``knowledge:index`` +
显式 admin 角色断言（与 AI 配置中心同一模式）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.knowledge_index_admin import (
    KnowledgeIndexRun,
)
from app.schemas.knowledge_index_admin import (
    JobResetRequest,
    KnowledgeIndexSettingRead,
    KnowledgeIndexSettingUpdate,
)
from app.services.knowledge_index_scheduler import (
    SchedulerBusyError,
    SchedulerDisabledError,
    admin_reset_jobs,
    compute_window,
    current_embedding_config,
    ensure_setting,
    ensure_state,
    get_scheduler,
    queue_overview,
)

router = APIRouter(prefix="/api/v1/knowledge-index", tags=["knowledge-index"])

_MAX_RUNS = 50


def _envelope(data, code: int = 200) -> dict:
    return {"code": code, "data": data}


def _require_admin(request: Request) -> None:
    """向量索引管理的显式 admin 校验（同 AI 配置中心）。"""
    if getattr(request.state, "role_code", None) != "admin":
        raise HTTPException(
            status_code=403, detail={"code": 40301, "msg": "无权限访问该资源"}
        )


async def _setting_read(db: AsyncSession) -> KnowledgeIndexSettingRead:
    row = await ensure_setting(db)
    return KnowledgeIndexSettingRead(
        enabled=row.enabled,
        timezone=row.timezone,
        window_start=row.window_start,
        window_end=row.window_end,
        safety_cutoff_minutes=row.safety_cutoff_minutes,
        reconcile_batch_size=row.reconcile_batch_size,
        embedding_batch_size=row.embedding_batch_size,
        request_interval_seconds=row.request_interval_seconds,
        request_timeout_seconds=row.request_timeout_seconds,
        max_attempts=row.max_attempts,
        backoff_base_seconds=row.backoff_base_seconds,
        backoff_max_seconds=row.backoff_max_seconds,
        dead_retention_days=row.dead_retention_days,
        stale_lock_minutes=row.stale_lock_minutes,
        run_now_max_products=row.run_now_max_products,
        run_now_max_duration_seconds=row.run_now_max_duration_seconds,
    )


def _run_to_dict(run: KnowledgeIndexRun) -> dict:
    return {
        "id": str(run.id),
        "trigger_type": run.trigger_type,
        "operator": run.operator,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "timezone": run.timezone_name,
        "window_start_at": run.window_start_at.isoformat() if run.window_start_at else None,
        "window_end_at": run.window_end_at.isoformat() if run.window_end_at else None,
        "cutoff_at": run.cutoff_at.isoformat() if run.cutoff_at else None,
        "scanned_count": run.scanned_count,
        "queued_count": run.queued_count,
        "embedding_success_count": run.embedding_success_count,
        "hash_skipped_count": run.hash_skipped_count,
        "failed_count": run.failed_count,
        "quarantined_count": run.quarantined_count,
        "batch_count": run.batch_count,
        "rate_limited_count": run.rate_limited_count,
        "stale_reclaimed_count": run.stale_reclaimed_count,
        "dead_purged_count": run.dead_purged_count,
        "backlog_before": run.backlog_before,
        "backlog_after": run.backlog_after,
        "embedding_model": run.embedding_model,
        "embedding_version": run.embedding_version,
        # token 用量：actual=上游实测；estimated=明确标注的估算值。二者互斥。
        "token_usage_actual": run.token_usage_actual,
        "token_usage_estimated": run.token_usage_estimated,
        "error_summary": run.error_summary,
        "details": run.details,
    }


@router.get("/settings", response_model=dict)
async def read_settings(
    request: Request,
    _current: dict = Depends(PermissionChecker("knowledge:index")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(request)
    settings_data = await _setting_read(db)
    state = await ensure_state(db)
    setting_row = await ensure_setting(db)
    plan = compute_window(setting_row, datetime.now(UTC))
    model, version, _tag = current_embedding_config()
    await db.commit()
    return _envelope(
        {
            "settings": settings_data.model_dump(),
            "scheduler": {
                "status": state.scheduler_status,
                "holder": state.holder,
                "heartbeat_at": state.heartbeat_at.isoformat() if state.heartbeat_at else None,
                "next_window_start_at": plan.next_start_utc.isoformat(),
                "next_cutoff_at": plan.cutoff_utc.isoformat(),
                "current_run_id": str(state.current_run_id) if state.current_run_id else None,
                "last_run_id": str(state.last_run_id) if state.last_run_id else None,
                "last_run_finished_at": (
                    state.last_run_finished_at.isoformat() if state.last_run_finished_at else None
                ),
            },
            "effective_embedding_model": model,
            "effective_embedding_version": version,
        }
    )


@router.put("/settings", response_model=dict)
@audit_action("knowledge_index_settings_update", module="knowledge_index")
async def update_settings(
    payload: KnowledgeIndexSettingUpdate,
    request: Request,
    _current: dict = Depends(PermissionChecker("knowledge:index")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(request)
    row = await ensure_setting(db)
    changes = payload.model_dump(exclude_none=True, exclude={"run_now_max_products"})
    if not changes and payload.run_now_max_products is not None:
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "msg": "run_now_max_products 为后端硬上限，不可修改"},
        )
    for field_name, value in changes.items():
        setattr(row, field_name, value)
    await db.commit()
    return _envelope((await _setting_read(db)).model_dump())


@router.get("/status", response_model=dict)
async def read_status(
    request: Request,
    _current: dict = Depends(PermissionChecker("knowledge:index")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(request)
    state = await ensure_state(db)
    setting_row = await ensure_setting(db)
    plan = compute_window(setting_row, datetime.now(UTC))
    queue = await queue_overview()
    current_run = None
    if state.current_run_id:
        row = await db.get(KnowledgeIndexRun, state.current_run_id)
        if row is not None:
            current_run = _run_to_dict(row)
    last_run = None
    if state.last_run_id:
        row = await db.get(KnowledgeIndexRun, state.last_run_id)
        if row is not None:
            last_run = _run_to_dict(row)
    heartbeat_stale = (
        state.heartbeat_at is None
        or (datetime.now(UTC) - state.heartbeat_at).total_seconds() > 120
    )
    await db.commit()
    return _envelope(
        {
            "enabled": setting_row.enabled,
            "scheduler_status": state.scheduler_status,
            "heartbeat_at": state.heartbeat_at.isoformat() if state.heartbeat_at else None,
            "heartbeat_stale": heartbeat_stale,
            "next_window_start_at": plan.next_start_utc.isoformat(),
            "next_cutoff_at": plan.cutoff_utc.isoformat(),
            "window_active": plan.active,
            "current_run": current_run,
            "last_run": last_run,
            "queue": queue,
        }
    )


@router.get("/runs", response_model=dict)
async def list_runs(
    request: Request,
    limit: int = 30,
    _current: dict = Depends(PermissionChecker("knowledge:index")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(request)
    limit = max(1, min(limit, _MAX_RUNS))
    result = await db.execute(
        select(KnowledgeIndexRun)
        .order_by(KnowledgeIndexRun.started_at.desc())
        .limit(limit)
    )
    runs = [_run_to_dict(run) for run in result.scalars().all()]
    await db.commit()
    return _envelope({"items": runs, "limit": limit})


@router.post("/run-now", response_model=dict)
@audit_action("knowledge_index_run_now", module="knowledge_index")
async def run_now(
    request: Request,
    _current: dict = Depends(PermissionChecker("knowledge:index")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(request)
    operator = str(request.state.user_id)
    try:
        result = await get_scheduler().try_start_run_now(
            operator=operator, operator_id=_operator_uuid(request)
        )
    except SchedulerBusyError as exc:
        raise HTTPException(status_code=409, detail={"code": 40901, "msg": str(exc)}) from exc
    except SchedulerDisabledError as exc:
        raise HTTPException(status_code=409, detail={"code": 40902, "msg": str(exc)}) from exc
    await db.commit()
    return _envelope(result)


def _operator_uuid(request: Request) -> UUID | None:
    raw = getattr(request.state, "user_id", None)
    try:
        return UUID(str(raw)) if raw else None
    except ValueError:
        return None


@router.post("/jobs/reset", response_model=dict)
@audit_action("knowledge_index_jobs_reset", module="knowledge_index")
async def reset_jobs(
    payload: JobResetRequest,
    request: Request,
    _current: dict = Depends(PermissionChecker("knowledge:index")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(request)
    job_ids: list[UUID] = []
    for raw in payload.job_ids or []:
        try:
            job_ids.append(UUID(raw))
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail={"code": 40001, "msg": f"非法 job id: {raw}"}
            ) from exc
    if not job_ids and payload.scope not in ("dead", "failed"):
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "msg": "必须提供 job_ids 或 scope=dead/failed"},
        )
    result = await admin_reset_jobs(
        job_ids=job_ids or None,
        scope=payload.scope,
        limit=payload.limit,
        operator=str(request.state.user_id),
        operator_id=_operator_uuid(request),
    )
    await db.commit()
    return _envelope(result)
