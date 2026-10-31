from __future__ import annotations

import asyncio
import os
import shutil
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    ai,
    ai_config,
    audit,
    auth,
    categories,
    health,
    knowledge,
    knowledge_index_admin,
    knowledge_sources,
    observability,
    pending_actions,
    products,
    proposal_floor_plans,
    proposals,
    roles,
    share_token,
    shares,
    users,
    version,
)
from app.api.v1.brands import router as brands_router
from app.api.v1.content import router as content_router
from app.api.v1.content_skills import router as content_skills_router
from app.api.v1.customers import router as customers_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.files import router as files_router
from app.api.v1.manuals import router as manuals_router
from app.api.v1.project_spaces import router as project_spaces_router
from app.api.v1.projects import router as projects_router
from app.api.v1.quotations import router as quotations_router
from app.api.v1.reminders import router as reminders_router
from app.api.v1.scene_images import router as scene_images_router
from app.api.v1.stats import router as stats_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.tags import router as tags_router
from app.core.config import settings
from app.core.security_limits import close_security_limits, is_internal_request
from app.middleware.audit import AuditMiddleware


async def _check_db() -> bool:
    """Lightweight DB reachability probe."""
    try:
        from app.core.database import engine

        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def _check_redis() -> bool:
    """Lightweight Redis reachability probe."""
    try:
        import redis.asyncio as redis

        client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
        await client.ping()
        await client.close()
        return True
    except Exception:  # noqa: BLE001
        return False


async def _check_minio() -> bool:
    """Probe the configured bucket without exposing connection details."""
    try:
        from app.core.minio_client import get_minio_client

        client = get_minio_client()
        await asyncio.wait_for(asyncio.to_thread(client.list_buckets), timeout=2.0)
        return True
    except Exception:  # noqa: BLE001
        return False


async def _check_ai_ready() -> bool:
    """AI is 'ready' when an adapter is configured (not NoneAdapter).

    This does NOT call the upstream — it only inspects local config/state so
    readiness is fast and does not cascade upstream failures into restart loops.
    """
    try:
        from app.adapters.factory import get_ai_adapter
        from app.adapters.none import NoneAdapter

        adapter = get_ai_adapter()
        return adapter is not None and not isinstance(adapter, NoneAdapter)
    except Exception:  # noqa: BLE001
        return False


async def _check_gotenberg() -> bool:
    """Probe Gotenberg health endpoint. Optional dependency — failure does not
    impact overall readiness (used for PDF quotation generation only).
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{settings.GOTENBERG_URL.rstrip('/')}/health")
            return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


async def _check_ocr_ready() -> bool:
    """OCR readiness: 'ok' only when an adapter is enabled AND its endpoint responds.
    When ``OCR_ADAPTER=none`` (V1.2 default) returns False; the health endpoint
    will surface this as ``disabled``, not as a fault.
    """
    adapter = (settings.OCR_ADAPTER or "none").lower()
    if adapter in ("", "none", "disabled"):
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.OCR_API_URL.rstrip('/')}/health")
            return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _volume_status() -> dict[str, dict[str, int | bool]]:
    """Report free bytes + threshold alert for directories that back our volumes.

    Returns empty dict if env not configured (pure unit environments).
    """
    threshold_env = os.environ.get("VOLUME_CAPACITY_WARN_BYTES")
    threshold = int(threshold_env) if threshold_env and threshold_env.isdigit() else 5 * 1024**3
    out: dict[str, dict[str, int | bool]] = {}
    targets = {
        "backups": os.environ.get("BACKUP_DIR", "backups"),
    }
    for name, path in targets.items():
        try:
            usage = shutil.disk_usage(os.path.abspath(path))
            from app.observability import metrics as _metrics

            _metrics.set_volume_free(name, usage.free, threshold)
            out[name] = {
                "free_bytes": int(usage.free),
                "threshold_bytes": threshold,
                "alert": usage.free < threshold,
            }
        except Exception:  # noqa: BLE001
            out[name] = {"free_bytes": -1, "threshold_bytes": threshold, "alert": False}
    return out


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Record startup timestamp for readiness / ops-status reporting.
    _app.state.started_at = time.time()
    # Warm the AI config cache (DB override layer) before serving traffic so the
    # first request already resolves provider settings instead of env-only.
    from app.services.ai_config import CACHE_TTL_SECONDS, refresh_cache

    try:
        await refresh_cache()
    except Exception:
        pass

    # 周期刷新：只在「启动 + 保存配置」时刷新是不够的——快照一旦过期，
    # 读路径就会回落 env，把管理员在 AI 配置中心显式改的模型/Key 静默丢回
    # 环境变量值（2026-10-28 实测：改模型后约 15 秒又变回 env 的旧模型）。
    # 这里用短于 TTL 的间隔持续续期，保证缓存始终是 DB 覆盖层的真值。
    async def _refresh_ai_config_loop() -> None:
        interval = max(1.0, CACHE_TTL_SECONDS / 3.0)
        while True:
            await asyncio.sleep(interval)
            try:
                await refresh_cache()
            except Exception:
                # DB 抖动时保留旧快照（refresh_cache 自身已保证），绝不清空。
                pass

    refresher = asyncio.create_task(_refresh_ai_config_loop())

    # 夜间向量索引调度（默认 Asia/Shanghai 01:00-02:30；见
    # app/services/knowledge_index_scheduler.py）。多 worker 下每个进程都有
    # 一个实例，谁拿到 advisory lock 谁干活，其余进程只做心跳。
    from app.services.knowledge_index_scheduler import start_scheduler, stop_scheduler

    start_scheduler()

    try:
        yield
    finally:
        await stop_scheduler()
        await close_security_limits()
        refresher.cancel()
        try:
            await refresher
        except asyncio.CancelledError:
            pass
    # Release adapter-held HTTP clients (e.g. OpenAIAdapter's httpx.AsyncClient).
    from app.adapters.factory import _cached_adapter, _cached_content_adapter

    for adapter in (_cached_adapter, _cached_content_adapter):
        if adapter is not None:
            try:
                await adapter.aclose()
            except Exception:
                pass


docs_enabled = settings.ENABLE_API_DOCS
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION or settings.VERSION,
    description="AI 产品信息管理平台 (AI-PIM) - Business API",
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)

cors_origins = [
    item.strip() for item in settings.CORS_ALLOW_ORIGINS.split(",") if item.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Device-Fingerprint", "X-Openid"],
    )

app.add_middleware(AuditMiddleware)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(observability.router, prefix="/api/v1", tags=["observability"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(roles.router, prefix="/api/v1/roles", tags=["roles"])
app.include_router(products.router, prefix="/api/v1/products", tags=["products"])
app.include_router(categories.router, prefix="/api/v1/categories", tags=["categories"])
app.include_router(brands_router, prefix="/api/v1/brands", tags=["brands"])
app.include_router(suppliers_router, prefix="/api/v1/suppliers", tags=["suppliers"])
app.include_router(tags_router, prefix="/api/v1/tags", tags=["tags"])
app.include_router(proposals.router, prefix="/api/v1/proposals", tags=["proposals"])
app.include_router(
    proposal_floor_plans.router,
    prefix="/api/v1/proposals/{proposal_id}/floor-plans",
    tags=["proposals"],
)
app.include_router(shares.router, prefix="/api/v1/shares", tags=["shares"])
app.include_router(share_token.router, prefix="/api/v1", tags=["shares"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(ai_config.router, tags=["ai-config"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(knowledge_sources.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(knowledge_index_admin.router, tags=["knowledge-index"])
app.include_router(pending_actions.router, prefix="/api/v1/ai/actions", tags=["ai"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(quotations_router, prefix="/api/v1/quotations", tags=["quotations"])
app.include_router(files_router, prefix="/api/v1/files", tags=["files"])
app.include_router(manuals_router, prefix="/api/v1/manuals", tags=["manuals"])
app.include_router(stats_router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(dashboard_router)
app.include_router(customers_router)
app.include_router(projects_router)
app.include_router(project_spaces_router)
app.include_router(content_router)
app.include_router(content_skills_router)
app.include_router(reminders_router)
app.include_router(scene_images_router, prefix="/api/v1/scene-images", tags=["scene_images"])
app.include_router(version.router, prefix="/api/v1", tags=["version"])


_READY_CACHE: tuple[float, dict[str, object]] | None = None


@app.get("/")
async def root():
    return {"code": 200, "data": {"message": "AI-PIM API"}}


# ---------------------------------------------------------------------------
# Kubernetes-style health probes
# ---------------------------------------------------------------------------


@app.get("/health/live", tags=["health"])
async def health_live():
    """Liveness probe — process is alive. Process-only, no dependency checks."""
    return {"status": "alive"}


async def _build_ready_payload() -> dict[str, object]:
    components: dict[str, str] = {}
    healthy = True

    if await _check_db():
        components["db"] = "ok"
    else:
        components["db"] = "error"
        healthy = False

    if await _check_redis():
        components["redis"] = "ok"
    else:
        components["redis"] = "error"
        # Redis is not fatal for readiness — the app can still serve non-AI routes.
        # But we report it so operators can see the degradation.

    if await _check_minio():
        components["minio"] = "ok"
    else:
        components["minio"] = "error"

    ai_adapter = getattr(settings, "AI_ADAPTER", None)
    ai_ready = await _check_ai_ready()
    if ai_ready:
        components["ai"] = "ok"
    elif ai_adapter and ai_adapter != "none":
        components["ai"] = "configured"
    else:
        components["ai"] = "none"

    # Optional capability probes: surface as disabled/ok/down without downgrading
    # overall readiness unless the SRE explicitly wires them as fatal.
    if await _check_gotenberg():
        components["gotenberg"] = "ok"
    else:
        components["gotenberg"] = "down"

    ocr_adapter = (settings.OCR_ADAPTER or "none").lower()
    if ocr_adapter in ("", "none", "disabled"):
        components["ocr"] = "disabled"
    elif await _check_ocr_ready():
        components["ocr"] = "ok"
    else:
        components["ocr"] = "down"

    # Capacity alert surfaces here but does NOT downgrade readiness (per V1.2
    # §5.2: low-risk capacity warnings must not flip readiness to NOT OK).
    volume_status = _volume_status()
    capacity_alert = any(
        (isinstance(v, dict) and v.get("alert", False)) for v in volume_status.values()
    )

    started_at = getattr(app.state, "started_at", None)
    status = "ready" if healthy else "degraded"
    return {
        "status": status,
        "ai_adapter": settings.AI_ADAPTER or "none",
        "ocr_adapter": settings.OCR_ADAPTER or "none",
        "started_at": started_at,
        "components": components,
        "volumes": volume_status,
        "capacity_alert": capacity_alert,
    }


@app.get("/health/ready", tags=["health"])
async def health_ready(request: Request = None):
    """Readiness probe — internal-only and cached in production."""
    global _READY_CACHE
    if request is not None and not is_internal_request(request):
        raise HTTPException(
            status_code=403,
            detail={"code": 40301, "msg": "仅内网可访问健康检查"},
        )
    if request is not None and settings.APP_ENV == "production" and _READY_CACHE:
        cached_at, payload = _READY_CACHE
        if time.monotonic() - cached_at < settings.HEALTH_READY_CACHE_SECONDS:
            return payload
    payload = await _build_ready_payload()
    if request is not None and settings.APP_ENV == "production":
        _READY_CACHE = (time.monotonic(), payload)
    return payload
