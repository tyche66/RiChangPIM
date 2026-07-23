from __future__ import annotations

import asyncio
import os
import shutil
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    ai,
    audit,
    auth,
    categories,
    health,
    observability,
    products,
    proposals,
    roles,
    share_token,
    shares,
    users,
    version,
)
from app.api.v1.brands import router as brands_router
from app.api.v1.files import router as files_router
from app.api.v1.manuals import router as manuals_router
from app.api.v1.quotations import router as quotations_router
from app.api.v1.scene_images import router as scene_images_router
from app.api.v1.stats import router as stats_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.tags import router as tags_router
from app.core.config import settings
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
    threshold = int(threshold_env) if threshold_env and threshold_env.isdigit() else 5 * 1024 ** 3
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
    yield
    # Release adapter-held HTTP clients (e.g. OpenAIAdapter's httpx.AsyncClient).
    from app.adapters.factory import _cached_adapter

    if _cached_adapter is not None:
        try:
            await _cached_adapter.aclose()
        except Exception:
            pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION or settings.VERSION,
    description="AI 产品信息管理平台 (AI-PIM) - Business API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(shares.router, prefix="/api/v1/shares", tags=["shares"])
app.include_router(share_token.router, prefix="/api/v1", tags=["shares"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(quotations_router, prefix="/api/v1/quotations", tags=["quotations"])
app.include_router(files_router, prefix="/api/v1/files", tags=["files"])
app.include_router(manuals_router, prefix="/api/v1/manuals", tags=["manuals"])
app.include_router(stats_router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(scene_images_router, prefix="/api/v1/scene-images", tags=["scene_images"])
app.include_router(version.router, prefix="/api/v1", tags=["version"])


@app.get("/")
async def root():
    return {
        "code": 200,
        "data": {"message": "AI-PIM API", "version": settings.APP_VERSION or settings.VERSION},
    }


# ---------------------------------------------------------------------------
# Kubernetes-style health probes
# ---------------------------------------------------------------------------

@app.get("/health/live", tags=["health"])
async def health_live():
    """Liveness probe — process is alive. Process-only, no dependency checks."""
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    """Readiness probe — process is alive AND critical dependencies are reachable.

    Checks DB, Redis, MinIO client construction, and AI config state.
    Does NOT leak internal URLs, keys, or stack traces.
    """
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
        "app_version": settings.APP_VERSION or settings.VERSION,
        "ai_adapter": settings.AI_ADAPTER or "none",
        "ocr_adapter": settings.OCR_ADAPTER or "none",
        "started_at": started_at,
        "components": components,
        "volumes": volume_status,
        "capacity_alert": capacity_alert,
    }
