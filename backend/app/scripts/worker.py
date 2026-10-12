"""提醒 worker（HLD §10.5）。

每 60s 扫 pending/snoozed 且到期者，FOR UPDATE SKIP LOCKED LIMIT 100。
每 10 tick 调用 reconcile_rules() / escalate_overdue()。
Redis 分布式锁 reminder_tick (ttl=50s) 保证多实例安全。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.reminder_rules import (
    dispatch_due_reminders,
    escalate_overdue,
    reconcile_rules,
)

logger = logging.getLogger(__name__)

HEARTBEAT_FILE = Path("/tmp/worker_heartbeat")
TICK_INTERVAL = 60
RECONCILE_INTERVAL = 10


def _now() -> datetime:
    return datetime.now(UTC)


async def _redis_lock(redis: aioredis.Redis, key: str, ttl: int) -> bool:
    """Try to acquire a Redis lock. Returns True if acquired."""
    acquired = await redis.set(key, "1", nx=True, ex=ttl)
    return acquired is not None


async def _heartbeat() -> None:
    HEARTBEAT_FILE.write_text(str(time.time()))


async def run_tick(db, now: datetime) -> None:
    """Single tick: dispatch due reminders."""
    dispatched = await dispatch_due_reminders(db, now=now, limit=100)
    if dispatched:
        logger.info("dispatched %d reminders", len(dispatched))


async def run_reconcile(db, now: datetime) -> None:
    """Reconcile rules and escalate overdue."""
    created = await reconcile_rules(db, now=now)
    if created:
        logger.info("reconcile created %d reminders", created)
    escalated = await escalate_overdue(db, now=now)
    if escalated:
        logger.info("escalated %d reminders", escalated)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("worker starting...")

    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    tick_count = 0

    try:
        while True:
            tick_count += 1
            lock_key = "reminder_tick"

            if await _redis_lock(redis, lock_key, ttl=50):
                try:
                    async with AsyncSessionLocal() as db:
                        now = _now()
                        await run_tick(db, now)

                        if tick_count % RECONCILE_INTERVAL == 0:
                            await run_reconcile(db, now)

                        await _heartbeat()
                except Exception:
                    logger.exception("tick failed")
            else:
                logger.debug("another worker holds the lock, skipping tick")

            await asyncio.sleep(TICK_INTERVAL)
    except asyncio.CancelledError:
        logger.info("worker shutting down...")
    finally:
        await redis.close()


if __name__ == "__main__":
    asyncio.run(main())
