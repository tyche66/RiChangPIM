"""内容条目状态机纯函数（HLD §5.3）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

TRANSITIONS: dict[str, list[str]] = {
    "draft": ["adopted", "rejected"],
    "adopted": ["produced", "published"],
    "produced": ["published"],
    "published": [],
    "rejected": [],
}

TERMINAL_STATES: frozenset[str] = frozenset({"published", "rejected"})

TRACKING_STATE = "tracking"
CLOSED_STATE = "closed"

CLOSED_AFTER_DAYS = 14

_BEIJING_TZ = timezone(timedelta(hours=8))


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in TRANSITIONS.get(from_status, [])


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATES


def validate_transition(from_status: str, to_status: str) -> dict:
    if not can_transition(from_status, to_status):
        return {"ok": False, "code": 40010, "msg": f"非法状态迁移: {from_status} -> {to_status}"}
    return {"ok": True}


def derive_display_state(
    item: Any,
    publications: list[Any],
    snapshots: list[Any],
    reminders: list[Any],
    *,
    now: datetime | None = None,
) -> str:
    if now is None:
        now = datetime.now(_BEIJING_TZ)

    status = item.status

    if status != "published":
        return status

    if not publications:
        return status

    pub_ids = {p.id for p in publications}
    has_snapshot = any(s.publication_id in pub_ids for s in snapshots)

    if not has_snapshot:
        return status

    if _is_closed(item, publications, reminders, now):
        return CLOSED_STATE

    return TRACKING_STATE


def _is_closed(
    item: Any,
    publications: list[Any],
    reminders: list[Any],
    now: datetime,
) -> bool:
    if not publications:
        return False

    latest_published_at = max(p.published_at for p in publications)
    if latest_published_at:
        latest_bj = latest_published_at.astimezone(_BEIJING_TZ)
        if (now - latest_bj) >= timedelta(days=CLOSED_AFTER_DAYS):
            return True

    pub_ids = {p.id for p in publications}
    r2_reminders = [
        r for r in reminders
        if r.rule_code == "content_metric_t7" and r.target_id in pub_ids
    ]
    if r2_reminders and all(r.status == "done" for r in r2_reminders):
        return True

    return False


def should_cache_closed_at(
    item: Any,
    publications: list[Any],
    snapshots: list[Any],
    reminders: list[Any],
    *,
    now: datetime | None = None,
) -> bool:
    if item.status != "published":
        return False
    if item.closed_at is not None:
        return False
    display = derive_display_state(item, publications, snapshots, reminders, now=now)
    return display == CLOSED_STATE
