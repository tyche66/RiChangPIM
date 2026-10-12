"""提醒规则引擎（HLD §10.2-10.3）。

纯函数 + DB 操作，不依赖 FastAPI。worker 每 60s 调用 dispatch_due_reminders，
每 10 tick 调用 reconcile_rules / escalate_overdue。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.reminder import Notification, Reminder

logger = logging.getLogger(__name__)

BIZ_TZ = ZoneInfo("Asia/Shanghai")
UTC = UTC

# Rule codes
R1 = "content_video_check"       # item -> adopted
R1B = "content_publish_check"     # item -> produced
R2_T1 = "content_metric_t1"       # publication +1d
R2_T3 = "content_metric_t3"       # publication +3d
R2_T7 = "content_metric_t7"       # publication +7d
R3 = "customer_follow_up"        # follow_up.next_follow_at
E1 = "escalation"                 # sent > 24h -> escalate to managers


def _now_utc() -> datetime:
    return datetime.now(UTC)


def due_at_for(base_utc: datetime, days: int, hour: int | None = None) -> datetime:
    """Compute due_at in UTC from a base UTC datetime + N days at hour (Asia/Shanghai).

    If REMINDER_SKIP_WEEKEND is true, shift weekend due dates to next Monday.
    """
    if hour is None:
        hour = settings.REMINDER_HOUR
    local = base_utc.astimezone(BIZ_TZ) + timedelta(days=days)
    local = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if settings.REMINDER_SKIP_WEEKEND and local.weekday() >= 5:
        local += timedelta(days=7 - local.weekday())
    return local.astimezone(UTC)


def _dedupe_key(rule_code: str, target_id: UUID, suffix: str = "") -> str:
    base = f"{rule_code}:{target_id}"
    return f"{base}:{suffix}" if suffix else base


async def create_reminders_for_event(
    event_type: str,
    entity: dict,
    db: AsyncSession,
) -> list[Reminder]:
    """Create reminders based on event type. Idempotent via dedupe_key.

    Events:
      - item_adopted: R1 reminder, due +2d@09:00, assignee=adopted_by
      - item_produced: R1b reminder, due +2d@09:00, assignee=produced_by or adopted_by
      - publication_created: R2 t1/t3/t7 reminders, assignee=item produced_by/adopted_by
      - follow_up_created: R3 reminder, due=next_follow_at, assignee=follower_id
    """
    created: list[Reminder] = []
    now = _now_utc()

    if event_type == "item_adopted":
        item_id = entity["id"]
        adopted_by = entity.get("adopted_by")
        adopted_at = entity.get("adopted_at") or now
        if not adopted_by:
            return created
        due = due_at_for(adopted_at, settings.REMINDER_ADOPT_DAYS)
        dedupe = _dedupe_key(R1, item_id)
        reminder = Reminder(
            rule_code=R1,
            target_type="content_item",
            target_id=item_id,
            assignee_id=adopted_by,
            title=f"内容视频检查: {entity.get('title', str(item_id))}",
            body="请在2天内完成视频检查。",
            due_at=due,
            status="pending",
            dedupe_key=dedupe,
            payload={"item_id": str(item_id), "adopted_at": adopted_at.isoformat()},
            created_by=adopted_by,
        )
        created.append(reminder)

    elif event_type == "item_produced":
        item_id = entity["id"]
        produced_by = entity.get("produced_by") or entity.get("adopted_by")
        produced_at = entity.get("produced_at") or now
        if not produced_by:
            return created
        due = due_at_for(produced_at, settings.REMINDER_PUBLISH_DAYS)
        dedupe = _dedupe_key(R1B, item_id)
        reminder = Reminder(
            rule_code=R1B,
            target_type="content_item",
            target_id=item_id,
            assignee_id=produced_by,
            title=f"内容发布检查: {entity.get('title', str(item_id))}",
            body="请在2天内完成发布检查。",
            due_at=due,
            status="pending",
            dedupe_key=dedupe,
            payload={"item_id": str(item_id), "produced_at": produced_at.isoformat()},
            created_by=produced_by,
        )
        created.append(reminder)

    elif event_type == "publication_created":
        pub_id = entity["id"]
        published_at = entity.get("published_at") or now
        assignee_id = entity.get("produced_by") or entity.get("adopted_by")
        if not assignee_id:
            return created
        item_title = entity.get("item_title", str(pub_id))
        for days, code in [(1, R2_T1), (3, R2_T3), (7, R2_T7)]:
            due = due_at_for(published_at, days)
            dedupe = _dedupe_key(code, pub_id)
            reminder = Reminder(
                rule_code=code,
                target_type="publication",
                target_id=pub_id,
                assignee_id=assignee_id,
                title=f"内容数据回收 T+{days}: {item_title}",
                body=f"请回收发布后第{days}天的数据。",
                due_at=due,
                status="pending",
                dedupe_key=dedupe,
                payload={"publication_id": str(pub_id), "t_days": days},
                created_by=assignee_id,
            )
            created.append(reminder)

    elif event_type == "follow_up_created":
        fu_id = entity["id"]
        next_follow_at = entity.get("next_follow_at")
        follower_id = entity.get("follower_id")
        if not next_follow_at or not follower_id:
            return created
        dedupe = _dedupe_key(R3, fu_id)
        reminder = Reminder(
            rule_code=R3,
            target_type="follow_up",
            target_id=fu_id,
            assignee_id=follower_id,
            title=f"客户跟进: {entity.get('content', str(fu_id))[:50]}",
            body="预约的跟进时间到了。",
            due_at=next_follow_at,
            status="pending",
            dedupe_key=dedupe,
            payload={"follow_up_id": str(fu_id)},
            created_by=follower_id,
        )
        created.append(reminder)

    # Upsert: skip if dedupe_key already exists (idempotent)
    result: list[Reminder] = []
    for rem in created:
        stmt = (
            pg_insert(Reminder)
            .values(
                rule_code=rem.rule_code,
                target_type=rem.target_type,
                target_id=rem.target_id,
                assignee_id=rem.assignee_id,
                title=rem.title,
                body=rem.body,
                due_at=rem.due_at,
                status=rem.status,
                dedupe_key=rem.dedupe_key,
                payload=rem.payload,
                created_by=rem.created_by,
            )
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
            .returning(Reminder.id)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row:
            rem.id = row
            result.append(rem)

    return result


async def close_reminders(dedupe_prefix: str, reason: str, db: AsyncSession) -> int:
    """Close reminders matching dedupe_prefix. Returns count of closed reminders."""
    stmt = (
        update(Reminder)
        .where(
            Reminder.dedupe_key.like(f"{dedupe_prefix}%"),
            Reminder.is_deleted.is_(False),
            Reminder.status.in_(["pending", "sent", "snoozed"]),
        )
        .values(status="done", done_at=_now_utc(), payload={"close_reason": reason})
        .returning(Reminder.id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return len(rows)


async def dispatch_due_reminders(
    db: AsyncSession,
    now: datetime | None = None,
    limit: int = 100,
) -> list[Reminder]:
    """Dispatch due reminders (pending/snoozed and due_at <= now).

    Uses FOR UPDATE SKIP LOCKED for multi-instance safety.
    Creates notifications and marks reminders as sent.
    """
    if now is None:
        now = _now_utc()

    stmt = (
        select(Reminder)
        .where(
            Reminder.is_deleted.is_(False),
            Reminder.status.in_(["pending", "snoozed"]),
            Reminder.due_at <= now,
        )
        .order_by(Reminder.due_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    reminders = list((await db.execute(stmt)).scalars().all())

    for rem in reminders:
        rem.status = "sent"
        rem.fired_at = now
        rem.attempts += 1
        # Create notification
        notif = Notification(
            user_id=rem.assignee_id,
            title=rem.title,
            body=rem.body,
            kind="reminder",
            link=f"/reminders/{rem.id}",
            reminder_id=rem.id,
            created_by=rem.assignee_id,
        )
        db.add(notif)

    if reminders:
        await db.commit()

    return reminders


async def reconcile_rules(db: AsyncSession, now: datetime | None = None) -> int:
    """Reconcile: find entities that should have reminders but don't.

    Scans content_items, content_publications, follow_ups for missing reminders.
    Returns count of new reminders created.
    """
    if now is None:
        now = _now_utc()
    count = 0

    # R1: adopted items without reminders
    from app.models.content import ContentItem
    stmt = (
        select(ContentItem)
        .where(
            ContentItem.status == "adopted",
            ContentItem.is_deleted.is_(False),
        )
    )
    items = (await db.execute(stmt)).scalars().all()
    for item in items:
        # Check if R1 reminder exists
        dedupe = _dedupe_key(R1, item.id)
        exists = (await db.execute(
            select(Reminder.id).where(Reminder.dedupe_key == dedupe, Reminder.is_deleted.is_(False))
        )).scalar_one_or_none()
        if not exists:
            rem = Reminder(
                rule_code=R1, target_type="content_item", target_id=item.id,
                assignee_id=item.adopted_by, title=f"内容视频检查: {item.title or ''}",
                body="请在2天内完成视频检查。",
                due_at=due_at_for(item.adopted_at or now, settings.REMINDER_ADOPT_DAYS),
                status="pending", dedupe_key=dedupe,
                payload={"item_id": str(item.id)}, created_by=item.adopted_by,
            )
            db.add(rem)
            count += 1

    # R3: follow_ups with next_follow_at and no reminder
    from app.models.sales import FollowUp
    stmt = (
        select(FollowUp)
        .where(
            FollowUp.done_at.is_(None),
            FollowUp.next_follow_at.is_not(None),
            FollowUp.is_deleted.is_(False),
        )
    )
    follow_ups = (await db.execute(stmt)).scalars().all()
    for fu in follow_ups:
        dedupe = _dedupe_key(R3, fu.id)
        exists = (await db.execute(
            select(Reminder.id).where(Reminder.dedupe_key == dedupe, Reminder.is_deleted.is_(False))
        )).scalar_one_or_none()
        if not exists:
            rem = Reminder(
                rule_code=R3, target_type="follow_up", target_id=fu.id,
                assignee_id=fu.follower_id, title="客户跟进",
                body="预约的跟进时间到了。",
                due_at=fu.next_follow_at,
                status="pending", dedupe_key=dedupe,
                payload={"follow_up_id": str(fu.id)}, created_by=fu.follower_id,
            )
            db.add(rem)
            count += 1

    if count:
        await db.commit()
    return count


async def escalate_overdue(db: AsyncSession, now: datetime | None = None) -> int:
    """Escalate reminders that have been 'sent' for > 24h without action.

    Creates escalation notifications for managers/admins.
    Returns count of escalations.
    """
    if now is None:
        now = _now_utc()
    threshold = now - timedelta(hours=settings.REMINDER_ESCALATE_HOURS)

    stmt = (
        select(Reminder)
        .where(
            Reminder.status == "sent",
            Reminder.fired_at <= threshold,
            Reminder.escalated.is_(False),
            Reminder.is_deleted.is_(False),
        )
        .limit(100)
        .with_for_update(skip_locked=True)
    )
    overdue = list((await db.execute(stmt)).scalars().all())

    escalated_count = 0
    for rem in overdue:
        rem.escalated = True
        rem.status = "overdue"
        # Create escalation notification for all managers/admins
        from app.models.user import User
        mgr_stmt = select(User.id).where(
            User.role_code.in_(["admin", "manager"]),
            User.is_deleted.is_(False),
        )
        managers = list((await db.execute(mgr_stmt)).scalars().all())
        for mgr_id in managers:
            notif = Notification(
                user_id=mgr_id,
                title=f"[升级] {rem.title}",
                body=f"提醒已发送超过{settings.REMINDER_ESCALATE_HOURS}小时未处理。",
                kind="escalation",
                link=f"/reminders/{rem.id}",
                reminder_id=rem.id,
                created_by=mgr_id,
            )
            db.add(notif)
        escalated_count += 1

    if escalated_count:
        await db.commit()
    return escalated_count
