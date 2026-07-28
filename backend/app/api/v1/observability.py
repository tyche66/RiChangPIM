"""V1.2 observability routes: ``/metrics`` and ``/ops/status``.

- ``GET /metrics`` (Prometheus text 1.0, no auth): scraped by external collectors.
- ``GET /ops/status`` (admin-only): human-readable operational snapshot.

Both intentionally return no secrets. Audit body redaction has its own policy
in ``app.middleware.audit`` — here we only expose aggregate state.
"""

from __future__ import annotations

import os
import shutil
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.config import settings
from app.core.permission import PermissionChecker
from app.observability import metrics

router = APIRouter()

_START_TIME = time.time()


@router.get("/metrics")
async def metrics_endpoint():
    # Refresh pool gauge from live engine before rendering.
    try:
        from app.core.database import engine

        pool = engine.pool
        avail = pool.available() if hasattr(pool, "available") else 0
        metrics.set_db_pool(pool.checkedout(), avail)
    except Exception:  # noqa: BLE001
        # Don't fail /metrics for a transient DB pool probe; gauges keep last value.
        pass

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(metrics.render_text(), media_type=metrics.CONTENT_TYPE)


@router.get("/observability/metrics")
async def metrics_endpoint_alias():
    return await metrics_endpoint()


@router.get("/ops/status")
async def ops_status(_user=Depends(PermissionChecker("audit:view"))):
    """Operational snapshot for SREs and pilot runners.

    Outputs aggregate state only. Never echoes credentials or request bodies.
    """
    payload: dict[str, object] = {
        "app_version": settings.APP_VERSION or settings.VERSION,
        "started_at": _START_TIME,
        "uptime_seconds": round(time.time() - _START_TIME, 3),
        "ai_adapter": settings.AI_ADAPTER or "none",
        "ocr_adapter": settings.OCR_ADAPTER or "none",
        "migration_head": await _current_migration_head(),
        "db_version": await _current_db_version(),
    }

    # Backup status (best-effort; missing dir is acceptable in non-prod).
    payload["backup"] = _backup_status_snapshot()

    # Capacity: check the directories that back our volumes.
    payload["volumes"] = _capacity_snapshot({
        "backups": os.environ.get("BACKUP_DIR", "backups"),
    })
    payload["knowledge"] = await _knowledge_status_snapshot()

    # 5xx count in last 24h (best-effort; reads from a rolling counter that
    # the audit middleware populates — see app.middleware.audit).
    from app.middleware.audit import http_5xx_last_24h

    payload["http_5xx_last_24h"] = http_5xx_last_24h()

    return {"code": 200, "data": payload}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _current_migration_head() -> str:
    """Return the current Alembic head version.

    Reads ``alembic_version`` table; no autoupgrade. Failure returns ``"unknown"``.
    """
    try:
        from sqlalchemy import text

        from app.core.database import engine

        async with engine.connect() as conn:
            row = (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).first()
            return str(row[0]) if row else "empty"
    except Exception:  # noqa: BLE001
        return "unknown"


async def _current_db_version() -> str:
    try:
        from sqlalchemy import text

        from app.core.database import engine

        async with engine.connect() as conn:
            row = (await conn.execute(text("SHOW server_version"))).first()
            return str(row[0]) if row else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


async def _knowledge_status_snapshot() -> dict[str, object]:
    try:
        from app.core.database import engine

        async with engine.connect() as conn:
            pending = (
                await conn.execute(
                    text(
                        "SELECT priority, count(*) FROM knowledge_index_job "
                        "WHERE is_deleted=false AND status IN ('pending','dispatched','failed') "
                        "GROUP BY priority"
                    )
                )
            ).fetchall()
            dead_jobs = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM knowledge_index_job "
                        "WHERE is_deleted=false AND status='dead'"
                    )
                )
            ).scalar() or 0
            active_chunks = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM knowledge_chunk "
                        "WHERE is_deleted=false"
                    )
                )
            ).scalar() or 0
        for priority, count in pending:
            metrics.set_knowledge_queue_depth(str(priority), int(count))
        metrics.set_knowledge_dead_jobs(int(dead_jobs))
        metrics.set_knowledge_chunks_active(int(active_chunks))
        return {
            "queue_depth": {str(priority): int(count) for priority, count in pending},
            "dead_jobs": int(dead_jobs),
            "active_chunks": int(active_chunks),
        }
    except Exception:  # noqa: BLE001
        return {"queue_depth": {}, "dead_jobs": -1, "active_chunks": -1}


def _backup_status_snapshot() -> dict[str, object]:
    backup_dir = os.environ.get("BACKUP_DIR", "backups")
    last_status_path = os.path.join(backup_dir, "last_status.json")
    if not os.path.exists(last_status_path):
        return {"available": False}
    try:
        import json

        with open(last_status_path, encoding="utf-8") as fh:
            return {"available": True, "data": json.load(fh)}
    except Exception:  # noqa: BLE001
        return {"available": False, "error": "unreadable"}


def _capacity_snapshot(targets: dict[str, str]) -> dict[str, dict[str, int | bool]]:
    """Return free bytes + alert flag for each tracked target."""
    threshold_env = os.environ.get("VOLUME_CAPACITY_WARN_BYTES")
    # Default threshold: 5 GiB; operators can override via env.
    threshold = int(threshold_env) if threshold_env and threshold_env.isdigit() else 5 * 1024 ** 3
    out: dict[str, dict[str, int | bool]] = {}
    for name, path in targets.items():
        abs_path = os.path.abspath(path)
        try:
            usage = shutil.disk_usage(abs_path)
            metrics.set_volume_free(name, usage.free, threshold)
            out[name] = {
                "free_bytes": int(usage.free),
                "threshold_bytes": threshold,
                "alert": usage.free < threshold,
            }
        except Exception:  # noqa: BLE001
            out[name] = {"free_bytes": -1, "threshold_bytes": threshold, "alert": False}
    return out
