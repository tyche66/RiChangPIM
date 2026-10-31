"""夜间产品向量索引调度服务（替代常驻 knowledge-indexer 进程）。

设计要点
========
- 调度：默认 Asia/Shanghai 每日 01:00-02:30 窗口内处理 ``knowledge_index_job``
  队列；窗口外完全空闲（没有每分钟全表扫描）。距窗口结束不足
  ``safety_cutoff_minutes``（默认 5 分钟，即 02:25）不再发起新的 embedding
  请求；窗口结束时未完成任务回到 pending 留在队列里，下一夜继续。
- 单例：任何索引活动（夜间窗口 / run-now / reconcile）都必须先拿到
  Postgres advisory lock（会话级，进程崩溃自动释放），多 uvicorn worker
  或过渡期旧 worker 并存时，同一产品只会被一个进程处理。
- 生命周期修复：
  * reconcile 只补"没有未终态任务"的产品；failed 任务按 ``next_attempt_at``
    退避，绝不被重置为立即 pending、不清空退避、不重置失败计数。
  * 最新任务为 dead 的产品保持隔离；只有产品卡内容 hash / pipeline /
    embedding model 变化，或管理员显式"重置重试"时才重新入队。
  * 确定性数据库错误（IntegrityError/DataError/ProgrammingError）把该任务
    标记为 dead（INDEX_DETERMINISTIC_ERROR）并隔离，不重试、不重复计费。
  * 429 指数退避且不消耗重试预算；瞬时错误指数退避并计入尝试次数。
  * embedding 前对比当前产品卡内容 hash + embedding model/version + 有效
    向量，完全匹配时跳过外部 API 调用（零计费）。
  * 逐产品 savepoint + 逐产品提交：单个产品写库失败只影响其自身。
  * 僵死 processing 任务（心跳超时）回收为 pending，保留失败计数。
- 清理：dead 任务保留 ``dead_retention_days``（默认 90）天，过期分批清理；
  pending/processing/未过期记录绝不清理。
- 报告：knowledge_index_run 记录触发者、计数、前后积压、模型版本、token
  用量（实测或明确标注的估算），错误摘要写入前统一脱敏。
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, exists, func, or_, select, text, update
from sqlalchemy.exc import DataError, IntegrityError, ProgrammingError
from sqlalchemy.orm import aliased

from app.adapters.base import AIServiceAdapter
from app.adapters.exceptions import AIAdapterError, AIAdapterRateLimitError
from app.adapters.factory import get_ai_adapter
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.knowledge.documents.base import KnowledgeDocumentUpserter
from app.knowledge.documents.product_card import DatabaseProductFactProvider
from app.knowledge.indexing.pipeline import KnowledgeIndexingPipeline
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeIndexJob
from app.models.knowledge_index_admin import (
    RUN_NOW_HARD_CAP,
    SETTING_SINGLETON_ID,
    STATE_SINGLETON_ID,
    KnowledgeIndexRun,
    KnowledgeIndexSchedulerState,
    KnowledgeIndexSetting,
)
from app.models.product import Brand, Category, Product, ProductTag, Tag
from app.services.ai_config import get_config

logger = logging.getLogger("knowledge_index_scheduler")

DETERMINISTIC_DB_ERRORS = (IntegrityError, DataError, ProgrammingError)
DETERMINISTIC_ERROR_CODE = "INDEX_DETERMINISTIC_ERROR"

#: 产品卡管线版本标签；embedding model / version 一并编码进去，
#: 使 dead 隔离判断能同时感知"内容 hash / pipeline / 模型"三类变化。
CARD_PIPELINE_VERSION = "product-card-v2"

#: 窗口内两次有界 reconcile 的间隔。窗口外绝不轮询。
RECONCILE_INTERVAL_SECONDS = 300.0

#: 调度主循环 tick 间隔（心跳/启停响应粒度）。
TICK_SECONDS = 20.0

_ADVISORY_LOCK_KEY = 768113001
_FALLBACK_TZ = timezone(timedelta(hours=8))

#: 本进程启动时刻（UTC）。启动恢复只收尾早于该时刻的 running 报告，绝不
#: 影响其他存活 worker 在同一晚已经开始的运行。
_PROCESS_STARTED_AT = datetime.now(UTC)

_SECRET_REGEXES = (
    re.compile(r"sk-[A-Za-z0-9_-]{6,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|token|authorization)\s*[=:]\s*[\"']?[A-Za-z0-9._\-]{8,}"),
)

_tz_cache: dict[str, object] = {}


class SchedulerBusyError(RuntimeError):
    """已有索引任务在运行（单例锁被占用）。"""


class SchedulerDisabledError(RuntimeError):
    """向量索引服务已停用。"""


# ---------------------------------------------------------------------------
# 小工具：时区 / 窗口 / 脱敏
# ---------------------------------------------------------------------------


def resolve_tz(name: str):
    """解析 IANA 时区；失败时 Asia/Shanghai 回落固定 +08:00。"""
    cached = _tz_cache.get(name)
    if cached is not None:
        return cached
    resolved = None
    try:
        from zoneinfo import ZoneInfo

        resolved = ZoneInfo(name)
    except Exception:  # noqa: BLE001 - 容器缺 tzdata 时保底
        if name in ("Asia/Shanghai", "PRC", "Asia/Chongqing", "Asia/Urumqi"):
            resolved = _FALLBACK_TZ
        else:
            resolved = UTC
    _tz_cache[name] = resolved
    return resolved


def parse_hhmm(value: str) -> time:
    parts = str(value or "").strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid HH:MM time: {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid HH:MM time: {value!r}")
    return time(hour=hour, minute=minute)


@dataclass(frozen=True)
class WindowPlan:
    """一次调度窗口的 UTC 边界。"""

    start_utc: datetime
    end_utc: datetime
    cutoff_utc: datetime
    next_start_utc: datetime
    active: bool


def compute_window(setting: KnowledgeIndexSetting, now_utc: datetime) -> WindowPlan:
    tz = resolve_tz(setting.timezone)
    local_now = now_utc.astimezone(tz)
    start_time = parse_hhmm(setting.window_start)
    end_time = parse_hhmm(setting.window_end)
    start_local = datetime.combine(local_now.date(), start_time, tzinfo=tz)
    end_local = datetime.combine(local_now.date(), end_time, tzinfo=tz)
    if end_local <= start_local:  # 支持跨午夜窗口
        end_local += timedelta(days=1)

    active = False
    if local_now >= end_local:
        next_start_local = start_local + timedelta(days=1)
    elif local_now >= start_local:
        active = True
        next_start_local = start_local + timedelta(days=1)
    elif start_time > end_time and local_now >= (start_local - timedelta(days=1)):
        # 跨午夜窗口：昨天的窗口还没走完（如 23:30-01:30，现在 00:15）。
        active = True
        start_local -= timedelta(days=1)
        end_local -= timedelta(days=1)
        next_start_local = start_local + timedelta(days=1)
    else:
        next_start_local = start_local

    cutoff_local = max(
        start_local, end_local - timedelta(minutes=setting.safety_cutoff_minutes)
    )

    return WindowPlan(
        start_utc=start_local.astimezone(UTC),
        end_utc=end_local.astimezone(UTC),
        cutoff_utc=cutoff_local.astimezone(UTC),
        next_start_utc=next_start_local.astimezone(UTC),
        active=active,
    )


def pipeline_tag(model: str, version: str | None) -> str:
    return f"{CARD_PIPELINE_VERSION}|emb={model}|ver={version or model}"


def current_embedding_config() -> tuple[str, str, str]:
    """(model, version, tag)：DB 覆盖层优先，回落环境变量。"""
    cfg = get_config("knowledge")
    model = cfg.embedding_model or settings.AI_EMBEDDING_MODEL
    version = settings.AI_EMBEDDING_VERSION or model
    return model, version, pipeline_tag(model, version)


def sanitize_text(value: str | None, *, secrets: set[str] | None = None) -> str:
    """错误信息脱敏：替换已知密钥值与常见密钥形态，压成单行截断。"""
    text_value = str(value or "").splitlines()[0] if value else ""
    for secret in secrets or set():
        if secret:
            text_value = text_value.replace(secret, "***")
    for pattern in _SECRET_REGEXES:
        text_value = pattern.sub("***", text_value)
    return text_value[:240]


async def collect_secret_roots() -> set[str]:
    """收集报告脱敏用的已知密钥明文（ai_provider_config + 环境变量）。"""
    secrets: set[str] = set()
    for value in (settings.AI_API_KEY, settings.AI_EMBEDDING_API_KEY):
        if value:
            secrets.add(str(value))
    try:
        from app.models.ai_config import AiProviderConfig

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(AiProviderConfig.api_key, AiProviderConfig.embedding_api_key).where(
                    AiProviderConfig.is_deleted.is_(False)
                )
            )
            for api_key, emb_key in rows.all():
                if api_key:
                    secrets.add(str(api_key))
                if emb_key:
                    secrets.add(str(emb_key))
    except Exception:  # noqa: BLE001 - 拿不到配置时仍有正则兜底
        logger.debug("collect_secret_roots failed", exc_info=True)
    return secrets


# ---------------------------------------------------------------------------
# 配置 / 运行态读写
# ---------------------------------------------------------------------------


async def ensure_setting(db) -> KnowledgeIndexSetting:
    row = await db.get(KnowledgeIndexSetting, UUID(SETTING_SINGLETON_ID))
    if row is not None:
        return row
    row = KnowledgeIndexSetting(id=UUID(SETTING_SINGLETON_ID))
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        row = await db.get(KnowledgeIndexSetting, UUID(SETTING_SINGLETON_ID))
    return row


async def ensure_state(db) -> KnowledgeIndexSchedulerState:
    row = await db.get(KnowledgeIndexSchedulerState, UUID(STATE_SINGLETON_ID))
    if row is not None:
        return row
    row = KnowledgeIndexSchedulerState(id=UUID(STATE_SINGLETON_ID), scheduler_status="idle")
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        row = await db.get(KnowledgeIndexSchedulerState, UUID(STATE_SINGLETON_ID))
    return row


async def load_settings() -> KnowledgeIndexSetting:
    async with AsyncSessionLocal() as db:
        row = await ensure_setting(db)
        await db.commit()
        return row


async def touch_heartbeat(
    *,
    holder: str,
    next_start: datetime | None = None,
    next_cutoff: datetime | None = None,
    status: str | None = None,
) -> None:
    """心跳与下次调度时间；status 仅在未被活动运行占用时才改写。"""
    async with AsyncSessionLocal() as db:
        state = await ensure_state(db)
        state.heartbeat_at = datetime.now(UTC)
        state.holder = holder
        if next_start is not None:
            state.next_window_start_at = next_start
        if next_cutoff is not None:
            state.next_cutoff_at = next_cutoff
        if status is not None and state.scheduler_status in ("idle", "disabled", status):
            state.scheduler_status = status
        await db.commit()


# ---------------------------------------------------------------------------
# 单例锁（Postgres advisory lock，会话级）
# ---------------------------------------------------------------------------


class SingletonLock:
    """索引活动互斥锁：持有期间独占一条连接上的 advisory lock。

    会话级锁在进程崩溃/连接断开时自动释放，不会死锁；未拿到锁立即返回
    False，调用方跳过本轮工作。
    """

    def __init__(self) -> None:
        self._conn = None
        self.acquired = False

    async def acquire(self) -> bool:
        from app.core.database import engine

        conn = await engine.connect()
        try:
            result = await conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}
            )
            self.acquired = bool(result.scalar())
        except Exception:  # noqa: BLE001
            self.acquired = False
        if self.acquired:
            self._conn = conn
        else:
            await conn.close()
        return self.acquired

    async def release(self) -> None:
        if self._conn is not None and self.acquired:
            try:
                await self._conn.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY}
                )
            except Exception:  # noqa: BLE001 - 连接关闭时锁随之释放
                pass
            try:
                await self._conn.close()
            except Exception:  # noqa: BLE001
                pass
        self._conn = None
        self.acquired = False

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, *exc_info) -> None:
        await self.release()


# ---------------------------------------------------------------------------
# 队列查询 / reconcile
# ---------------------------------------------------------------------------


def _active_job_exists(source_id, operation: str):
    job = aliased(KnowledgeIndexJob)
    return exists(
        select(1).select_from(job).where(
            job.source_type == "product_card",
            job.source_id == source_id,
            job.operation == operation,
            job.status.in_(("pending", "dispatched", "processing", "failed")),
            job.is_deleted.is_(False),
        )
    )


def _dead_job_exists(source_id, operation: str):
    job = aliased(KnowledgeIndexJob)
    return exists(
        select(1).select_from(job).where(
            job.source_type == "product_card",
            job.source_id == source_id,
            job.operation == operation,
            job.status == "dead",
            job.is_deleted.is_(False),
        )
    )


def _product_card_needs_indexing(*, include_dead_blocked: bool):
    """待索引产品查询。

    ``include_dead_blocked=False``：排除有 dead 任务的产品（直接入队组）。
    ``include_dead_blocked=True``：只返回有 dead 任务的产品（hash 对比组）。
    两种情况都要求当前没有未终态任务——failed 任务保持退避，绝不被
    reconcile 重置为立即 pending。
    """
    document = aliased(KnowledgeDocument)
    chunk = aliased(KnowledgeChunk)
    product_tag = aliased(ProductTag)
    tag = aliased(Tag)
    brand = aliased(Brand)
    category = aliased(Category)
    last_indexed = document.last_indexed_at
    model, _version, _tag_str = current_embedding_config()

    tag_changed = exists(
        select(1)
        .select_from(product_tag)
        .join(tag, tag.id == product_tag.tag_id, isouter=True)
        .where(
            product_tag.product_id == Product.id,
            product_tag.is_deleted.is_(False),
            or_(
                last_indexed.is_(None),
                product_tag.update_time > last_indexed,
                tag.update_time > last_indexed,
            ),
        )
    )
    brand_changed = exists(
        select(1)
        .select_from(brand)
        .where(
            brand.id == Product.brand_id,
            or_(last_indexed.is_(None), brand.update_time > last_indexed),
        )
    )
    category_changed = exists(
        select(1)
        .select_from(category)
        .where(
            category.id == Product.category_id,
            or_(last_indexed.is_(None), category.update_time > last_indexed),
        )
    )

    dead_filter = (
        _dead_job_exists(Product.id, "upsert")
        if include_dead_blocked
        else ~_dead_job_exists(Product.id, "upsert")
    )

    return (
        select(Product.id)
        .select_from(Product)
        .outerjoin(
            document,
            and_(
                document.source_type == "product_card",
                document.source_id == Product.id,
                document.is_deleted.is_(False),
            ),
        )
        .outerjoin(
            chunk,
            and_(chunk.document_id == document.id, chunk.is_deleted.is_(False)),
        )
        .where(
            Product.is_deleted.is_(False),
            ~_active_job_exists(Product.id, "upsert"),
            dead_filter,
            or_(
                document.id.is_(None),
                document.index_status != "indexed",
                document.last_indexed_at.is_(None),
                chunk.id.is_(None),
                chunk.embedding.is_(None),
                chunk.embedding_model.is_(None),
                chunk.embedding_model != model,
                Product.vector.is_(None),
                Product.update_time > document.last_indexed_at,
                tag_changed,
                brand_changed,
                category_changed,
            ),
        )
        .group_by(Product.id, Product.update_time)
        .order_by(Product.update_time.asc())
    )


def _orphan_product_card_documents():
    document = aliased(KnowledgeDocument)
    return (
        select(document.source_id)
        .select_from(document)
        .where(
            document.source_type == "product_card",
            document.source_id.is_not(None),
            document.is_deleted.is_(False),
            document.is_active.is_(True),
            ~exists(
                select(1).where(
                    Product.id == document.product_id,
                    Product.is_deleted.is_(False),
                )
            ),
            ~_active_job_exists(document.source_id, "delete"),
        )
    )


async def _sync_existing_product_vectors(db) -> int:
    """把已建好的卡片向量回填到 product.vector（纯 DB，无外部调用）。"""
    result = await db.execute(
        text(
            """
            UPDATE product AS p
               SET vector = kc.embedding,
                   update_time = p.update_time
              FROM knowledge_document AS kd
              JOIN knowledge_chunk AS kc ON kc.document_id = kd.id
             WHERE p.id = kd.product_id
               AND p.is_deleted = false
               AND p.vector IS NULL
               AND kd.source_type = 'product_card'
               AND kd.is_deleted = false
               AND kd.is_active = true
               AND kd.index_status = 'indexed'
               AND kc.is_deleted = false
               AND kc.embedding IS NOT NULL
            """
        )
    )
    return result.rowcount or 0


async def _enqueue_upsert(
    db,
    product_id: UUID,
    *,
    content_hash: str | None,
    tag: str,
    max_attempts: int,
) -> bool:
    """新建 upsert 任务。不触碰既有 failed/dead 任务（保留退避与隔离）。

    savepoint 包住插入：活动（pending/dispatched/processing）唯一索引冲突
    时只回滚这一条，竞态下等下一轮 reconcile 再处理。
    """
    try:
        async with db.begin_nested():
            db.add(
                KnowledgeIndexJob(
                    source_type="product_card",
                    source_id=product_id,
                    operation="upsert",
                    status="pending",
                    content_hash=content_hash,
                    pipeline_version=tag,
                    priority=10,
                    max_attempts=max_attempts,
                )
            )
            await db.flush()
        return True
    except DETERMINISTIC_DB_ERRORS:
        logger.warning("enqueue upsert raced for product %s; skipped this round", product_id)
        return False


async def reconcile_once(*, batch_size: int) -> dict:
    """有界 reconcile：入队待索引产品 + 孤儿下线任务 + 僵死锁回收。

    候选集由索引条件查询给出，上限 ``batch_size``；不做全表重扫。
    """
    now = datetime.now(UTC)
    _model, _version, tag = current_embedding_config()
    result = {
        "scanned": 0,
        "queued": 0,
        "synced_vectors": 0,
        "stale_reclaimed": 0,
        "blocked_dead": 0,
    }

    async with AsyncSessionLocal() as db:
        setting = await ensure_setting(db)

        # 僵死 processing 回收：保留失败计数（中断恢复，不是失败重置）。
        stale_before = now - timedelta(minutes=setting.stale_lock_minutes)
        reclaim = await db.execute(
            update(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.status == "processing",
                KnowledgeIndexJob.is_deleted.is_(False),
                or_(
                    KnowledgeIndexJob.heartbeat_at.is_(None),
                    KnowledgeIndexJob.heartbeat_at < stale_before,
                ),
            )
            .values(
                status="pending",
                locked_by=None,
                locked_at=None,
                heartbeat_at=now,
            )
        )
        result["stale_reclaimed"] = reclaim.rowcount or 0

        result["synced_vectors"] += await _sync_existing_product_vectors(db)

        # 组一：没有 dead 任务的产品，直接入队。
        rows = (
            await db.execute(
                _product_card_needs_indexing(include_dead_blocked=False).limit(batch_size)
            )
        ).all()
        result["scanned"] += len(rows)
        for (product_id,) in rows:
            if await _enqueue_upsert(
                db, product_id, content_hash=None, tag=tag, max_attempts=setting.max_attempts
            ):
                result["queued"] += 1

        # 组二：有 dead 任务的产品（隔离区）——只有内容 hash / pipeline /
        # embedding model 变化时才重新入队。
        dead_rows = (
            await db.execute(
                _product_card_needs_indexing(include_dead_blocked=True).limit(batch_size)
            )
        ).all()
        result["scanned"] += len(dead_rows)
        for (product_id,) in dead_rows:
            latest_dead = (
                await db.execute(
                    select(KnowledgeIndexJob)
                    .where(
                        KnowledgeIndexJob.source_type == "product_card",
                        KnowledgeIndexJob.source_id == product_id,
                        KnowledgeIndexJob.operation == "upsert",
                        KnowledgeIndexJob.status == "dead",
                        KnowledgeIndexJob.is_deleted.is_(False),
                    )
                    .order_by(KnowledgeIndexJob.create_time.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            try:
                payload = await DatabaseProductFactProvider(db).build_product_card(product_id)
            except ValueError:
                continue  # 产品已不存在/为空：交由孤儿下线逻辑处理
            if latest_dead is not None and (
                latest_dead.content_hash == payload.content_hash
                and latest_dead.pipeline_version == tag
            ):
                result["blocked_dead"] += 1
                continue
            if await _enqueue_upsert(
                db,
                product_id,
                content_hash=payload.content_hash,
                tag=tag,
                max_attempts=setting.max_attempts,
            ):
                result["queued"] += 1

        orphan_budget = max(0, batch_size - result["scanned"])
        if orphan_budget:
            orphan_result = await db.execute(
                _orphan_product_card_documents().limit(orphan_budget)
            )
            for (source_id,) in orphan_result.all():
                if source_id is None:
                    continue
                try:
                    async with db.begin_nested():
                        db.add(
                            KnowledgeIndexJob(
                                source_type="product_card",
                                source_id=UUID(str(source_id)),
                                operation="delete",
                                status="pending",
                                pipeline_version=tag,
                                priority=20,
                                max_attempts=setting.max_attempts,
                            )
                        )
                        await db.flush()
                    result["queued"] += 1
                except DETERMINISTIC_DB_ERRORS:
                    logger.warning("enqueue orphan delete raced for %s", source_id)

        await db.commit()

    if result["queued"] or result["stale_reclaimed"]:
        logger.info(
            "reconcile: queued=%s stale_reclaimed=%s blocked_dead=%s",
            result["queued"],
            result["stale_reclaimed"],
            result["blocked_dead"],
        )
    return result


async def purge_dead_jobs(*, retention_days: int, batch_size: int = 500) -> int:
    """分批清理超过保留期的 dead 记录；pending/processing/未过期绝不触碰。"""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    total = 0
    while True:
        async with AsyncSessionLocal() as db:
            subq = (
                select(KnowledgeIndexJob.id)
                .where(
                    KnowledgeIndexJob.status == "dead",
                    func.coalesce(
                        KnowledgeIndexJob.completed_at, KnowledgeIndexJob.create_time
                    )
                    < cutoff,
                )
                .limit(batch_size)
            )
            result = await db.execute(
                delete(KnowledgeIndexJob).where(KnowledgeIndexJob.id.in_(subq))
            )
            await db.commit()
            removed = result.rowcount or 0
        total += removed
        if removed < batch_size:
            break
        await asyncio.sleep(0.2)
    return total


# ---------------------------------------------------------------------------
# 任务领取 / 状态标记
# ---------------------------------------------------------------------------


def _newer_active_job_exists():
    """同组 (source_type, source_id, operation) 是否存在更新的非终态任务。

    领取时只允许"最新一条"非终态任务被处理：历史 failed 与新 pending/
    processing 并存时，绝不在同一次运行里对同一产品发起两次 embedding。
    """
    newer = aliased(KnowledgeIndexJob)
    # 注意：同一事务内入队的任务 create_time 相同（PG now() 是事务时间戳），
    # 必须用 (create_time, id) 元组比较做确定性"更新"判断，保证同组
    # 非终态任务里恰好只有一条可领取，绝不重复 embedding。
    return exists(
        select(1).where(
            newer.source_type == KnowledgeIndexJob.source_type,
            newer.source_id == KnowledgeIndexJob.source_id,
            newer.operation == KnowledgeIndexJob.operation,
            newer.status.in_(("pending", "dispatched", "processing", "failed")),
            newer.is_deleted.is_(False),
            or_(
                newer.create_time > KnowledgeIndexJob.create_time,
                and_(
                    newer.create_time == KnowledgeIndexJob.create_time,
                    newer.id > KnowledgeIndexJob.id,
                ),
            ),
        )
    )


def _release_lock_values(now: datetime) -> dict:
    return {"locked_by": None, "locked_at": None, "heartbeat_at": now}


async def _claim_card_jobs(
    db, *, limit: int, source_ids: set[UUID] | None
) -> list[KnowledgeIndexJob]:
    """领取一批产品卡 upsert 任务；排除同一产品更新的 pending 任务。"""
    now = datetime.now(UTC)
    conditions = [
        KnowledgeIndexJob.source_type == "product_card",
        KnowledgeIndexJob.operation == "upsert",
        KnowledgeIndexJob.is_deleted.is_(False),
        KnowledgeIndexJob.status.in_(("pending", "dispatched", "failed")),
        or_(
            KnowledgeIndexJob.next_attempt_at.is_(None),
            KnowledgeIndexJob.next_attempt_at <= now,
        ),
        ~_newer_active_job_exists(),
    ]
    if source_ids is not None:
        if not source_ids:
            return []
        conditions.append(KnowledgeIndexJob.source_id.in_(source_ids))
    result = await db.execute(
        select(KnowledgeIndexJob)
        .where(*conditions)
        .order_by(KnowledgeIndexJob.priority.asc(), KnowledgeIndexJob.create_time.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    jobs = list(result.scalars().all())
    for job in jobs:
        job.status = "processing"
        job.locked_by = "nightly-scheduler"
        job.locked_at = now
        job.heartbeat_at = now
        job.started_at = job.started_at or now
    await db.commit()  # 声明领取；此后逐产品提交，不持有整批行锁
    return jobs


async def _claim_single_job(db, *, embedding_allowed: bool) -> KnowledgeIndexJob | None:
    """领取一个非"产品卡 upsert"任务（delete / 说明书等）。"""
    now = datetime.now(UTC)
    conditions = [
        KnowledgeIndexJob.is_deleted.is_(False),
        KnowledgeIndexJob.status.in_(("pending", "dispatched", "failed")),
        or_(
            KnowledgeIndexJob.next_attempt_at.is_(None),
            KnowledgeIndexJob.next_attempt_at <= now,
        ),
        ~_newer_active_job_exists(),
        or_(
            KnowledgeIndexJob.operation == "delete",
            KnowledgeIndexJob.source_type != "product_card",
        ),
    ]
    if not embedding_allowed:
        # 安全截止后只允许无 embedding 的下线任务继续。
        conditions.append(KnowledgeIndexJob.operation == "delete")
    result = await db.execute(
        select(KnowledgeIndexJob)
        .where(*conditions)
        .order_by(KnowledgeIndexJob.priority.asc(), KnowledgeIndexJob.create_time.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None
    job.status = "processing"
    job.locked_by = "nightly-scheduler"
    job.locked_at = now
    job.heartbeat_at = now
    job.started_at = job.started_at or now
    await db.commit()
    return job


def _mark_job_succeeded(job: KnowledgeIndexJob) -> None:
    now = datetime.now(UTC)
    job.status = "succeeded"
    job.completed_at = now
    job.next_attempt_at = None
    job.error_code = None
    job.error_message = None
    job.locked_by = None
    job.locked_at = None
    job.heartbeat_at = now


async def _mark_jobs_failed_fresh(
    job_ids: list[UUID],
    *,
    dead: bool,
    error_code: str,
    message: str,
    backoff_seconds: float | None = None,
    increment_attempt: bool = False,
) -> None:
    """在全新会话中记录失败（原会话可能已被数据库错误污染）。

    ``increment_attempt``：超时/上游错误等可重试失败必须递增 attempt_count，
    否则 max_attempts 永远达不到、任务每晚重复重试；429 不递增（不耗预算）。
    """
    if not job_ids:
        return
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as fail_db:
        values: dict = {
            "status": "dead" if dead else "failed",
            "error_code": error_code,
            "error_message": sanitize_text(message),
            "locked_by": None,
            "locked_at": None,
            "heartbeat_at": now,
        }
        if increment_attempt:
            values["attempt_count"] = KnowledgeIndexJob.attempt_count + 1
        if dead:
            values["completed_at"] = now
            values["next_attempt_at"] = None
        else:
            values["next_attempt_at"] = (
                now + timedelta(seconds=backoff_seconds) if backoff_seconds else None
            )
        await fail_db.execute(
            update(KnowledgeIndexJob).where(KnowledgeIndexJob.id.in_(job_ids)).values(**values)
        )
        await fail_db.commit()


def backoff_seconds(setting: KnowledgeIndexSetting, attempt_count: int) -> float:
    """指数退避：base * 2^attempt，封顶 backoff_max。"""
    delay = setting.backoff_base_seconds * (2 ** max(0, attempt_count))
    return float(min(delay, setting.backoff_max_seconds))


@dataclass
class BatchCounters:
    embedding_success: int = 0
    hash_skipped: int = 0
    quarantined: int = 0
    failed: int = 0
    dead: int = 0  # SOURCE_NOT_FOUND / SOURCE_EMPTY 等终态失败
    deferred: int = 0
    rate_limited: int = 0
    batches: int = 0
    tokens_actual: int = 0
    tokens_estimated: int = 0
    transacted: int = 0  # 本次实际尝试的任务数

    def merge(self, other: BatchCounters) -> None:
        for name in (
            "embedding_success", "hash_skipped", "quarantined", "failed", "dead",
            "deferred", "rate_limited", "batches", "tokens_actual", "tokens_estimated",
            "transacted",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))


@dataclass
class BatchOutcome:
    counters: BatchCounters = field(default_factory=BatchCounters)
    product_ids: list[UUID] = field(default_factory=list)


async def _find_fresh_embedding(db, payload, model: str, version: str):
    """内容 hash + 模型 + 版本 + 有效向量全部匹配时返回既有向量（零调用）。"""
    chunk_payload = payload.chunks[0].finalized()
    stmt = (
        select(KnowledgeChunk.embedding, Product.vector.label("product_vector"))
        .select_from(KnowledgeChunk)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .outerjoin(Product, Product.id == KnowledgeDocument.product_id)
        .where(
            KnowledgeDocument.source_type == payload.source_type,
            KnowledgeDocument.source_id == payload.source_id,
            KnowledgeDocument.is_deleted.is_(False),
            KnowledgeDocument.index_status == "indexed",
            KnowledgeDocument.content_hash == payload.content_hash,
            KnowledgeChunk.is_deleted.is_(False),
            KnowledgeChunk.chunk_index == chunk_payload.chunk_index,
            KnowledgeChunk.content_hash == chunk_payload.content_hash,
            KnowledgeChunk.embedding.is_not(None),
            KnowledgeChunk.embedding_model == model,
            KnowledgeChunk.embedding_version == version,
        )
        .limit(1)
    )
    return (await db.execute(stmt)).first()


async def process_product_card_batch(
    *,
    setting: KnowledgeIndexSetting,
    allow_embedding: bool,
    source_ids: set[UUID] | None = None,
    max_products: int | None = None,
) -> BatchOutcome:
    """领取最多一个 embedding 批次的产品卡任务并处理（逐产品提交）。

    任一产品写库失败只回滚该产品的 savepoint，并按错误类型把该产品标记为
    隔离（dead）或退避重试；其他产品已经逐个提交，不受影响。
    """
    outcome = BatchOutcome()
    counters = outcome.counters
    now = datetime.now(UTC)
    model, version, _tag = current_embedding_config()
    limit = setting.embedding_batch_size
    if max_products is not None:
        limit = min(limit, max_products)
    if limit <= 0:
        return outcome

    async with AsyncSessionLocal() as db:
        jobs = await _claim_card_jobs(db, limit=limit, source_ids=source_ids)
        if not jobs:
            return outcome

        payloads: list[tuple[KnowledgeIndexJob, object]] = []
        for job in jobs:
            outcome.product_ids.append(job.source_id)
            counters.transacted += 1
            try:
                payload = await DatabaseProductFactProvider(db).build_product_card(job.source_id)
            except ValueError as exc:
                job.status = "dead"
                job.error_code = (
                    "SOURCE_NOT_FOUND" if "not found" in str(exc) else "SOURCE_EMPTY"
                )
                job.error_message = sanitize_text(str(exc))
                job.completed_at = now
                job.locked_by = None
                job.locked_at = None
                counters.dead += 1
                continue
            # 把当前内容 hash / 管线标签写回任务行，失败后 dead 隔离
            # 才能判断"内容是否变化"。
            job.content_hash = payload.content_hash
            job.pipeline_version = pipeline_tag(model, version)
            payloads.append((job, payload))
        await db.commit()

        need_embedding: list[tuple[KnowledgeIndexJob, object]] = []
        for job, payload in payloads:
            matched = None
            try:
                matched = await _find_fresh_embedding(db, payload, model, version)
            except Exception:  # noqa: BLE001 - 查询失败按不匹配处理
                logger.debug("fresh-embedding lookup failed", exc_info=True)
            if matched is not None:
                try:
                    async with db.begin_nested():
                        if matched.product_vector is None and payload.product_id:
                            await db.execute(
                                update(Product)
                                .where(Product.id == payload.product_id)
                                .values(vector=matched.embedding)
                            )
                        _mark_job_succeeded(job)
                    await db.commit()
                    counters.hash_skipped += 1
                    continue
                except DETERMINISTIC_DB_ERRORS as exc:
                    await db.rollback()
                    await _mark_jobs_failed_fresh(
                        [job.id],
                        dead=True,
                        error_code=DETERMINISTIC_ERROR_CODE,
                        message=str(exc),
                    )
                    counters.quarantined += 1
                    continue
            need_embedding.append((job, payload))

        if not need_embedding:
            return outcome

        if not allow_embedding:
            # 安全截止/窗口结束：任务回到 pending（不动退避与失败计数），
            # 留在队列里等下一夜。
            async with AsyncSessionLocal() as fdb:
                await fdb.execute(
                    update(KnowledgeIndexJob)
                    .where(KnowledgeIndexJob.id.in_([job.id for job, _ in need_embedding]))
                    .values(status="pending", **_release_lock_values(now))
                )
                await fdb.commit()
            counters.deferred = len(need_embedding)
            return outcome

        # 快照任务元数据：rollback 会 expire ORM 对象，之后只能用普通值。
        jobs_meta = [
            {
                "job": job,
                "payload": payload,
                "job_id": job.id,
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
            }
            for job, payload in need_embedding
        ]
        texts = [
            payload.chunks[0].finalized().normalized_text or payload.chunks[0].chunk_text
            for meta in jobs_meta
            for payload in [meta["payload"]]
        ]
        adapter: AIServiceAdapter = get_ai_adapter()
        try:
            vectors, usage = await asyncio.wait_for(
                adapter.embed_with_usage(texts),
                timeout=float(setting.request_timeout_seconds) + 30.0,
            )
            if len(vectors) != len(jobs_meta):
                raise ValueError(
                    f"embedding count ({len(vectors)}) does not match "
                    f"product cards ({len(jobs_meta)})"
                )
        except TimeoutError:
            await db.rollback()
            for meta in jobs_meta:
                attempts = meta["attempt_count"] + 1
                await _mark_jobs_failed_fresh(
                    [meta["job_id"]],
                    dead=attempts >= meta["max_attempts"],
                    error_code="INDEX_UPSERT_FAILED",
                    message=f"embedding request timeout after {setting.request_timeout_seconds}s",
                    backoff_seconds=backoff_seconds(setting, attempts),
                    increment_attempt=True,
                )
            counters.failed += len(jobs_meta)
            return outcome
        except AIAdapterRateLimitError as exc:
            await db.rollback()
            for meta in jobs_meta:
                # 429 不消耗重试预算，按指数退避让窗口/下一夜自然消化。
                await _mark_jobs_failed_fresh(
                    [meta["job_id"]],
                    dead=False,
                    error_code="INDEX_RATE_LIMITED",
                    message=str(exc),
                    backoff_seconds=backoff_seconds(setting, meta["attempt_count"]),
                )
            counters.rate_limited += len(jobs_meta)
            return outcome
        except AIAdapterError as exc:
            await db.rollback()
            for meta in jobs_meta:
                attempts = meta["attempt_count"] + 1
                await _mark_jobs_failed_fresh(
                    [meta["job_id"]],
                    dead=attempts >= meta["max_attempts"],
                    error_code="INDEX_UPSERT_FAILED",
                    message=str(exc),
                    backoff_seconds=backoff_seconds(setting, attempts),
                    increment_attempt=True,
                )
            counters.failed += len(jobs_meta)
            return outcome
        except Exception as exc:  # noqa: BLE001 - 未知上游/网络错误按瞬时失败
            await db.rollback()
            for meta in jobs_meta:
                attempts = meta["attempt_count"] + 1
                await _mark_jobs_failed_fresh(
                    [meta["job_id"]],
                    dead=attempts >= meta["max_attempts"],
                    error_code="INDEX_UPSERT_FAILED",
                    message=str(exc),
                    backoff_seconds=backoff_seconds(setting, attempts),
                    increment_attempt=True,
                )
            counters.failed += len(jobs_meta)
            return outcome

        counters.batches += 1
        if usage and usage.get("total_tokens"):
            counters.tokens_actual += int(usage["total_tokens"])
        else:
            counters.tokens_estimated += max(1, sum(len(t) for t in texts) // 4)

        secrets = await collect_secret_roots()
        indexed_at = datetime.now(UTC)
        for meta, vector in zip(jobs_meta, vectors, strict=False):
            job = meta["job"]
            payload = meta["payload"]
            job_id = meta["job_id"]
            max_attempts = meta["max_attempts"]
            try:
                chunk = payload.chunks[0].finalized()
                chunk.embedding = vector
                chunk.embedding_model = model
                chunk.embedding_version = version
                payload.chunks = [chunk]
                payload.index_status = "indexed"
                payload.last_indexed_at = indexed_at
                async with db.begin_nested():
                    await KnowledgeDocumentUpserter(db).upsert(payload)
                    await db.execute(
                        update(Product)
                        .where(Product.id == payload.product_id, Product.is_deleted.is_(False))
                        .values(vector=vector)
                    )
                    _mark_job_succeeded(job)
                await db.commit()  # 逐产品提交：单产品失败不回滚其他产品
                counters.embedding_success += 1
            except DETERMINISTIC_DB_ERRORS as exc:
                # savepoint 已回滚，其他产品已提交；本产品隔离，不再重试计费。
                try:
                    job.status = "dead"
                    job.error_code = DETERMINISTIC_ERROR_CODE
                    job.error_message = sanitize_text(str(exc), secrets=secrets)
                    job.completed_at = datetime.now(UTC)
                    job.locked_by = None
                    job.locked_at = None
                    await db.commit()
                except Exception:  # noqa: BLE001 - 连接被污染时走新会话
                    await db.rollback()
                    await _mark_jobs_failed_fresh(
                        [job_id],
                        dead=True,
                        error_code=DETERMINISTIC_ERROR_CODE,
                        message=str(exc),
                    )
                counters.quarantined += 1
            except Exception as exc:  # noqa: BLE001
                attempts = meta["attempt_count"] + 1
                try:
                    job.attempt_count = attempts
                    job.error_code = "INDEX_UPSERT_FAILED"
                    job.error_message = sanitize_text(str(exc), secrets=secrets)
                    job.locked_by = None
                    job.locked_at = None
                    if attempts >= max_attempts:
                        job.status = "dead"
                        job.completed_at = datetime.now(UTC)
                        job.next_attempt_at = None
                    else:
                        job.status = "failed"
                        job.next_attempt_at = datetime.now(UTC) + timedelta(
                            seconds=backoff_seconds(setting, attempts)
                        )
                    await db.commit()
                except Exception:  # noqa: BLE001
                    await db.rollback()
                    await _mark_jobs_failed_fresh(
                        [job_id],
                        dead=attempts >= max_attempts,
                        error_code="INDEX_UPSERT_FAILED",
                        message=str(exc),
                        backoff_seconds=backoff_seconds(setting, attempts),
                        increment_attempt=True,
                    )
                counters.failed += 1
    return outcome


async def process_single_job(
    *, setting: KnowledgeIndexSetting, allow_embedding: bool
) -> BatchOutcome:
    """处理一个 delete / 说明书等单任务（savepoint 隔离）。"""
    outcome = BatchOutcome()
    counters = outcome.counters
    async with AsyncSessionLocal() as db:
        job = await _claim_single_job(db, embedding_allowed=allow_embedding)
        if job is None:
            return outcome
        counters.transacted += 1
        if job.source_id is not None:
            outcome.product_ids.append(job.source_id)
        # 快照：rollback 会 expire 对象，之后只能用普通值。
        job_id = job.id
        attempt_count = job.attempt_count
        max_attempts = job.max_attempts
        operation = job.operation
        source_type = job.source_type
        source_id = job.source_id
        pipeline = KnowledgeIndexingPipeline(db)
        try:
            if operation == "delete":
                await pipeline.delete_source(source_type, source_id)
            else:
                await pipeline.upsert_source(source_type, source_id)
            _mark_job_succeeded(job)
            await db.commit()
        except DETERMINISTIC_DB_ERRORS as exc:
            await db.rollback()
            await _mark_jobs_failed_fresh(
                [job_id], dead=True, error_code=DETERMINISTIC_ERROR_CODE, message=str(exc)
            )
            counters.quarantined += 1
        except AIAdapterRateLimitError as exc:
            await db.rollback()
            await _mark_jobs_failed_fresh(
                [job_id],
                dead=False,
                error_code="INDEX_RATE_LIMITED",
                message=str(exc),
                backoff_seconds=backoff_seconds(setting, attempt_count),
            )
            counters.rate_limited += 1
        except AIAdapterError as exc:
            await db.rollback()
            attempts = attempt_count + 1
            await _mark_jobs_failed_fresh(
                [job_id],
                dead=attempts >= max_attempts,
                error_code="INDEX_UPSERT_FAILED",
                message=str(exc),
                backoff_seconds=backoff_seconds(setting, attempts),
            )
            counters.failed += 1
        except ValueError as exc:
            await db.rollback()
            code = "SOURCE_NOT_FOUND" if "not found" in str(exc) else "SOURCE_EMPTY"
            await _mark_jobs_failed_fresh([job_id], dead=True, error_code=code, message=str(exc))
            counters.dead += 1
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            attempts = attempt_count + 1
            await _mark_jobs_failed_fresh(
                [job_id],
                dead=attempts >= max_attempts,
                error_code="INDEX_UPSERT_FAILED",
                message=str(exc),
                backoff_seconds=backoff_seconds(setting, attempts),
            )
            counters.failed += 1
    return outcome


# ---------------------------------------------------------------------------
# 运行编排
# ---------------------------------------------------------------------------


async def _executable_backlog() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.count())
            .select_from(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.is_deleted.is_(False),
                KnowledgeIndexJob.status.in_(("pending", "dispatched", "failed")),
            )
        )
        return int(result.scalar() or 0)


async def _scheduled_run_exists(plan: WindowPlan) -> bool:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.count())
            .select_from(KnowledgeIndexRun)
            .where(
                KnowledgeIndexRun.trigger_type == "scheduled",
                KnowledgeIndexRun.window_start_at == plan.start_utc,
                KnowledgeIndexRun.status.in_(("running", "completed", "stopped")),
            )
        )
        return bool(result.scalar())


async def _is_enabled() -> bool:
    async with AsyncSessionLocal() as db:
        row = await db.get(KnowledgeIndexSetting, UUID(SETTING_SINGLETON_ID))
        return bool(row.enabled) if row is not None else True


async def _next_due_at() -> datetime | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.min(KnowledgeIndexJob.next_attempt_at)).where(
                KnowledgeIndexJob.is_deleted.is_(False),
                KnowledgeIndexJob.status.in_(("pending", "dispatched", "failed")),
                KnowledgeIndexJob.next_attempt_at.is_not(None),
            )
        )
        return result.scalar()


async def _sleep_interruptible(seconds: float, stop_event: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(0.0, seconds))
    except TimeoutError:
        pass


async def recover_stale_running() -> int:
    """进程启动恢复：把"本进程启动前"遗留的 running 报告收尾为 stopped。

    多 worker 部署下，每个进程启动都会调用本函数。判断依据必须是报告
    ``started_at`` 与本进程启动时间的先后，而不是"超过 5 分钟"：

    - 启动那一刻本进程不可能已经在跑索引，因此 ``started_at`` 早于本进程
      启动时间的 running 报告只可能来自已退出的旧进程，可以回收；
    - ``started_at`` 晚于本进程启动时间的 running 报告属于其他存活 worker
      正在进行的运行，即便耗时超过 5 分钟也绝不能改写。

    旧实现用"早于 now-5min"做条件，并在末尾无条件 ``current_run_id=None``，
    结果是某个 worker 重启就会把一个活跃运行的报告标成 stopped、并清掉全局
    当前运行指针；这里改为按进程启动时间判断，诊断的僵死任务由窗口内的
    reconcile 依据 stale_lock_minutes 回收，两份职责不再混用。
    """
    now = datetime.now(UTC)
    stale_condition = (
        KnowledgeIndexRun.status == "running",
        KnowledgeIndexRun.started_at < _PROCESS_STARTED_AT,
    )
    async with AsyncSessionLocal() as db:
        stale_ids = list(
            (await db.execute(select(KnowledgeIndexRun.id).where(*stale_condition)))
            .scalars()
            .all()
        )
        fixed = 0
        if stale_ids:
            result = await db.execute(
                update(KnowledgeIndexRun)
                .where(KnowledgeIndexRun.id.in_(stale_ids))
                .values(
                    status="stopped",
                    finished_at=now,
                    error_summary="服务重启前未正常收尾（进程退出）",
                )
                .returning(KnowledgeIndexRun.id)
            )
            fixed = len(result.all())
            # 只清空指向“刚被回收的旧 run”的指针；其他存活 worker 正在写的
            # current_run_id 不受影响（其 run 的 started_at 晚于本进程启动）。
            state = await ensure_state(db)
            if state.current_run_id in set(stale_ids):
                state.current_run_id = None
        await db.commit()
    if fixed:
        logger.warning("recovered %s stale running run report(s) on startup", fixed)
    return fixed


class KnowledgeIndexScheduler:
    """每个后端进程一个实例；advisory lock 仲裁谁真正干活。"""

    def __init__(self) -> None:
        self.worker_id = f"sched-{socket.gethostname()}-{uuid4().hex[:8]}"
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._local_lock = asyncio.Lock()
        self._stopping = False

    # -- 生命周期 ---------------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event = asyncio.Event()
            self._stopping = False
            self._task = asyncio.create_task(
                self._run_loop(), name="knowledge-index-scheduler"
            )

    async def stop(self) -> None:
        self._stopping = True
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - 退出优先
                pass
            self._task = None

    async def _run_loop(self) -> None:
        try:
            await recover_stale_running()
        except Exception:  # noqa: BLE001 - 恢复失败不阻塞调度循环
            logger.exception("startup recovery of stale runs failed")
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 调度循环永不退出
                logger.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=TICK_SECONDS)
            except TimeoutError:
                pass

    async def _tick(self) -> None:
        setting = await load_settings()
        plan = compute_window(setting, datetime.now(UTC))
        await touch_heartbeat(
            holder=self.worker_id,
            next_start=plan.next_start_utc,
            next_cutoff=plan.cutoff_utc,
        )
        if not setting.enabled:
            await touch_heartbeat(holder=self.worker_id, status="disabled")
            return
        if not plan.active:
            return
        if self._local_lock.locked():
            return
        async with self._local_lock:
            async with SingletonLock() as locked:
                if not locked:
                    return
                if await _scheduled_run_exists(plan):
                    return
                logger.info(
                    "nightly window opens: %s .. %s (cutoff %s)",
                    plan.start_utc,
                    plan.end_utc,
                    plan.cutoff_utc,
                )
                await self._execute_run(
                    trigger="scheduled",
                    operator="system",
                    operator_id=None,
                    setting=setting,
                    plan=plan,
                )

    # -- 运行体 -----------------------------------------------------------

    async def _execute_run(
        self,
        *,
        trigger: str,
        operator: str,
        operator_id: UUID | None,
        setting: KnowledgeIndexSetting,
        plan: WindowPlan | None,
        product_cap: int | None = None,
        duration_seconds: int | None = None,
    ) -> dict:
        now = datetime.now(UTC)
        model, version, _tag = current_embedding_config()
        if trigger == "scheduled" and plan is not None:
            emb_deadline = plan.cutoff_utc
            hard_end = plan.end_utc
        else:
            emb_deadline = now + timedelta(
                seconds=duration_seconds or setting.run_now_max_duration_seconds
            )
            hard_end = emb_deadline

        counters = BatchCounters()
        scanned = 0
        queued = 0
        synced_vectors = 0
        dead_purged = 0
        stale_reclaimed = 0
        stop_reason = "queue_empty"
        errors: list[str] = []

        run = KnowledgeIndexRun(
            trigger_type=trigger,
            operator=operator,
            operator_id=operator_id,
            status="running",
            started_at=now,
            timezone_name=setting.timezone,
            window_start_at=plan.start_utc if plan else None,
            window_end_at=plan.end_utc if plan else None,
            cutoff_at=emb_deadline,
            embedding_model=model,
            embedding_version=version,
            backlog_before=await _executable_backlog(),
        )
        async with AsyncSessionLocal() as db:
            db.add(run)
            state = await ensure_state(db)
            state.scheduler_status = (
                "window_active" if trigger == "scheduled" else "run_now_active"
            )
            state.holder = self.worker_id
            state.current_run_id = run.id
            await db.commit()
        run_id = run.id
        logger.info(
            "index run %s (%s) starts; backlog=%s", run_id, trigger, run.backlog_before
        )

        try:
            # 窗口开始：dead 过期清理 + 一次有界 reconcile。
            dead_purged = await purge_dead_jobs(retention_days=setting.dead_retention_days)
            reconciled = await reconcile_once(batch_size=setting.reconcile_batch_size)
            scanned += reconciled.get("scanned", 0)
            queued += reconciled.get("queued", 0)
            synced_vectors += reconciled.get("synced_vectors", 0)
            stale_reclaimed += reconciled.get("stale_reclaimed", 0)

            attempted_products: set[UUID] = set()
            last_reconcile = datetime.now(UTC)

            while True:
                if self._stopping or self._stop_event.is_set():
                    stop_reason = "stopping"
                    break
                now = datetime.now(UTC)
                if now >= hard_end:
                    stop_reason = "window_end"
                    break
                if not await _is_enabled():
                    stop_reason = "disabled"
                    break

                allow_embedding = now < emb_deadline
                if not allow_embedding:
                    # 安全截止后：只处理无 embedding 的下线任务。
                    single = await process_single_job(
                        setting=setting, allow_embedding=False
                    )
                    if single.counters.transacted:
                        counters.merge(single.counters)
                        await self._flush_run_counters(
                            run_id, counters, scanned, queued, dead_purged,
                            stale_reclaimed,
                        )
                        await touch_heartbeat(holder=self.worker_id)
                        continue
                    stop_reason = "cutoff"
                    break

                cap_left = None
                if product_cap is not None:
                    cap_left = product_cap - len(attempted_products)
                    if cap_left <= 0:
                        stop_reason = "product_cap"
                        break

                batch = await process_product_card_batch(
                    setting=setting,
                    allow_embedding=True,
                    max_products=cap_left,
                )
                if batch.counters.transacted:
                    counters.merge(batch.counters)
                    attempted_products.update(
                        pid for pid in batch.product_ids if pid is not None
                    )
                    await self._flush_run_counters(
                        run_id, counters, scanned, queued, dead_purged,
                        stale_reclaimed,
                    )
                    await touch_heartbeat(holder=self.worker_id)
                    if batch.counters.batches:
                        await asyncio.sleep(
                            max(0.0, float(setting.request_interval_seconds))
                        )
                    continue

                single = await process_single_job(setting=setting, allow_embedding=True)
                if single.counters.transacted:
                    counters.merge(single.counters)
                    await self._flush_run_counters(
                        run_id, counters, scanned, queued, dead_purged,
                        stale_reclaimed,
                    )
                    await touch_heartbeat(holder=self.worker_id)
                    continue

                # 当前没有可执行任务：窗口内定期补充 reconcile。
                now = datetime.now(UTC)
                if (now - last_reconcile).total_seconds() >= RECONCILE_INTERVAL_SECONDS:
                    reconciled = await reconcile_once(
                        batch_size=setting.reconcile_batch_size
                    )
                    scanned += reconciled.get("scanned", 0)
                    queued += reconciled.get("queued", 0)
                    synced_vectors += reconciled.get("synced_vectors", 0)
                    stale_reclaimed += reconciled.get("stale_reclaimed", 0)
                    last_reconcile = now
                    if reconciled.get("queued"):
                        continue

                next_due = await _next_due_at()
                if next_due is not None and next_due < hard_end:
                    await _sleep_interruptible(
                        min(30.0, max(1.0, (next_due - datetime.now(UTC)).total_seconds())),
                        self._stop_event,
                    )
                    continue
                stop_reason = "queue_empty"
                break
        except asyncio.CancelledError:
            # 进程停止打断运行：报告必须落终态，不能永远停在 running。
            logger.warning("index run %s cancelled; finalizing as stopped", run_id)
            await self._finalize_run(
                run_id,
                counters,
                scanned=scanned,
                queued=queued,
                dead_purged=dead_purged,
                stale_reclaimed=stale_reclaimed,
                stop_reason="stopping",
                status="stopped",
                error=None,
                synced_vectors=synced_vectors,
            )
            raise
        except Exception as exc:  # noqa: BLE001 - 运行级异常：报告标 failed
            logger.exception("index run %s failed", run_id)
            errors.append(sanitize_text(str(exc), secrets=await collect_secret_roots()))
            await self._finalize_run(
                run_id,
                counters,
                scanned=scanned,
                queued=queued,
                dead_purged=dead_purged,
                stale_reclaimed=stale_reclaimed,
                stop_reason=stop_reason,
                status="failed",
                error=errors[0] if errors else None,
                synced_vectors=synced_vectors,
            )
            return {"run_id": str(run_id), "status": "failed"}

        status = "stopped" if stop_reason in ("disabled", "stopping") else "completed"
        await self._finalize_run(
            run_id,
            counters,
            scanned=scanned,
            queued=queued,
            dead_purged=dead_purged,
            stale_reclaimed=stale_reclaimed,
            stop_reason=stop_reason,
            status=status,
            error="; ".join(errors) if errors else None,
            synced_vectors=synced_vectors,
        )
        logger.info("index run %s finished: %s (%s)", run_id, status, stop_reason)
        return {"run_id": str(run_id), "status": status, "stop_reason": stop_reason}

    async def _flush_run_counters(
        self,
        run_id: UUID,
        counters: BatchCounters,
        scanned: int,
        queued: int,
        dead_purged: int,
        stale_reclaimed: int = 0,
    ) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(KnowledgeIndexRun)
                .where(KnowledgeIndexRun.id == run_id)
                .values(
                    scanned_count=scanned,
                    queued_count=queued,
                    embedding_success_count=counters.embedding_success,
                    hash_skipped_count=counters.hash_skipped,
                    failed_count=counters.failed + counters.dead,
                    quarantined_count=counters.quarantined,
                    rate_limited_count=counters.rate_limited,
                    batch_count=counters.batches,
                    stale_reclaimed_count=stale_reclaimed,
                    dead_purged_count=dead_purged,
                    token_usage_actual=counters.tokens_actual or None,
                    token_usage_estimated=counters.tokens_estimated or None,
                )
            )
            await db.commit()

    async def _finalize_run(
        self,
        run_id: UUID,
        counters: BatchCounters,
        *,
        scanned: int,
        queued: int,
        dead_purged: int,
        stale_reclaimed: int,
        stop_reason: str,
        status: str,
        error: str | None = None,
        synced_vectors: int = 0,
    ) -> None:
        now = datetime.now(UTC)
        enabled = await _is_enabled()
        async with AsyncSessionLocal() as db:
            run = await db.get(KnowledgeIndexRun, run_id)
            if run is not None:
                run.status = status
                run.finished_at = now
                run.scanned_count = scanned
                run.queued_count = queued
                run.embedding_success_count = counters.embedding_success
                run.hash_skipped_count = counters.hash_skipped
                run.failed_count = counters.failed + counters.dead
                run.quarantined_count = counters.quarantined
                run.batch_count = counters.batches
                run.rate_limited_count = counters.rate_limited
                run.stale_reclaimed_count = stale_reclaimed
                run.dead_purged_count = dead_purged
                run.backlog_after = await _executable_backlog()
                run.token_usage_actual = counters.tokens_actual or None
                run.token_usage_estimated = counters.tokens_estimated or None
                run.error_summary = error
                run.details = {
                    "stop_reason": stop_reason,
                    "synced_vectors": synced_vectors,
                    "token_usage_source": (
                        "provider"
                        if counters.tokens_actual
                        else ("estimated" if counters.tokens_estimated else None)
                    ),
                }
            state = await ensure_state(db)
            state.current_run_id = None
            state.last_run_id = run_id
            state.last_run_finished_at = now
            state.scheduler_status = "idle" if enabled else "disabled"
            state.holder = None
            await db.commit()

    # -- run-now ----------------------------------------------------------

    async def run_now_sync(
        self,
        *,
        operator: str,
        operator_id: UUID | None = None,
        duration_seconds: int | None = None,
    ) -> dict:
        """同步执行一次 run-now（CLI/运维入口，与 API 共用同一套约束）。

        - 服务停用时拒绝（enabled=false 不发起新任务）；
        - 进程内 asyncio.Lock + 跨进程 Postgres advisory lock 双重互斥，
          与夜间窗口不可能重叠；
        - 产品上限固定为 RUN_NOW_HARD_CAP（200），不受任何配置影响。
        """
        setting = await load_settings()
        if not setting.enabled:
            raise SchedulerDisabledError("向量索引服务已停用（enabled=false）；请先在后台启用")
        if self._local_lock.locked():
            raise SchedulerBusyError("本进程已有索引任务在运行")
        await self._local_lock.acquire()
        lock = SingletonLock()
        try:
            if not await lock.acquire():
                self._local_lock.release()
                raise SchedulerBusyError("其他进程正在执行索引任务（夜间窗口或手动运行）")
        except BaseException:
            if self._local_lock.locked():
                self._local_lock.release()
            raise
        try:
            return await self._execute_run(
                trigger="run_now",
                operator=operator,
                operator_id=operator_id,
                setting=setting,
                plan=None,
                product_cap=RUN_NOW_HARD_CAP,
                duration_seconds=(
                    duration_seconds
                    if duration_seconds is not None
                    else setting.run_now_max_duration_seconds
                ),
            )
        finally:
            await lock.release()
            if self._local_lock.locked():
                self._local_lock.release()

    async def try_start_run_now(self, *, operator: str, operator_id: UUID | None) -> dict:
        """管理员手动触发；200 产品上限与单例锁都在这里强制。"""
        setting = await load_settings()
        if not setting.enabled:
            raise SchedulerDisabledError("向量索引服务已停用，请先启用再手动运行")
        if self._local_lock.locked():
            raise SchedulerBusyError("本进程已有索引任务在运行")
        await self._local_lock.acquire()
        lock = SingletonLock()
        try:
            if not await lock.acquire():
                self._local_lock.release()
                raise SchedulerBusyError("其他进程正在执行索引任务（夜间窗口或手动运行）")
        except Exception:
            if self._local_lock.locked():
                self._local_lock.release()
            raise

        async def _runner() -> None:
            try:
                await self._execute_run(
                    trigger="run_now",
                    operator=operator,
                    operator_id=operator_id,
                    setting=setting,
                    plan=None,
                    product_cap=RUN_NOW_HARD_CAP,
                    duration_seconds=setting.run_now_max_duration_seconds,
                )
            except Exception:  # noqa: BLE001
                logger.exception("run-now execution failed")
            finally:
                await lock.release()
                if self._local_lock.locked():
                    self._local_lock.release()

        asyncio.create_task(_runner(), name="knowledge-index-run-now")
        return {
            "accepted": True,
            "max_products": RUN_NOW_HARD_CAP,
            "max_duration_seconds": setting.run_now_max_duration_seconds,
        }


# ---------------------------------------------------------------------------
# 模块级单例与查询助手（供 API / CLI 使用）
# ---------------------------------------------------------------------------

_scheduler: KnowledgeIndexScheduler | None = None


def get_scheduler() -> KnowledgeIndexScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = KnowledgeIndexScheduler()
    return _scheduler


def start_scheduler() -> None:
    get_scheduler().start()


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        await _scheduler.stop()
        _scheduler = None


async def queue_overview() -> dict:
    """队列概况：按状态计数 + 隔离/过期统计（不暴露任何凭据）。"""
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        setting = await ensure_setting(db)
        retention_days = setting.dead_retention_days
        rows = await db.execute(
            select(KnowledgeIndexJob.status, func.count())
            .where(KnowledgeIndexJob.is_deleted.is_(False))
            .group_by(KnowledgeIndexJob.status)
        )
        by_status = {status: int(count) for status, count in rows.all()}
        quarantined = await db.execute(
            select(func.count())
            .select_from(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.is_deleted.is_(False),
                KnowledgeIndexJob.status == "dead",
                KnowledgeIndexJob.error_code == DETERMINISTIC_ERROR_CODE,
            )
        )
        dead_cutoff = now - timedelta(days=retention_days)
        dead_expired = await db.execute(
            select(func.count())
            .select_from(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.status == "dead",
                KnowledgeIndexJob.is_deleted.is_(False),
                func.coalesce(KnowledgeIndexJob.completed_at, KnowledgeIndexJob.create_time)
                < dead_cutoff,
            )
        )
        dead_retained = await db.execute(
            select(func.count())
            .select_from(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.status == "dead",
                KnowledgeIndexJob.is_deleted.is_(False),
                func.coalesce(KnowledgeIndexJob.completed_at, KnowledgeIndexJob.create_time)
                >= dead_cutoff,
            )
        )
        oldest_dead = await db.execute(
            select(
                func.min(
                    func.coalesce(
                        KnowledgeIndexJob.completed_at, KnowledgeIndexJob.create_time
                    )
                )
            ).where(KnowledgeIndexJob.status == "dead", KnowledgeIndexJob.is_deleted.is_(False))
        )
        await db.commit()
    oldest = oldest_dead.scalar()
    backlog = sum(by_status.get(s, 0) for s in ("pending", "dispatched", "failed"))
    return {
        "by_status": by_status,
        "backlog": backlog,
        "quarantined": int(quarantined.scalar() or 0),
        "dead_retention_days": retention_days,
        "dead_expired_purgeable": int(dead_expired.scalar() or 0),
        "dead_retained": int(dead_retained.scalar() or 0),
        "oldest_dead_at": oldest.isoformat() if oldest else None,
    }


async def admin_reset_jobs(
    *,
    job_ids: list[UUID] | None = None,
    scope: str | None = None,
    limit: int = 200,
    operator: str,
    operator_id: UUID | None = None,
) -> dict:
    """授权的重置重试：为 dead/failed 任务的产品新建 pending 任务。

    不清空原任务记录（保留错误历史与失败计数）；新建任务带上当前管线
    标签，使 reconcile 的 dead 隔离判断立即放行。
    """
    if not job_ids and scope not in ("dead", "failed"):
        raise ValueError("必须指定 job_ids 或 scope（dead/failed）")
    _model, _version, tag = current_embedding_config()
    reset = 0
    async with AsyncSessionLocal() as db:
        conditions = [KnowledgeIndexJob.is_deleted.is_(False)]
        if job_ids:
            conditions.append(KnowledgeIndexJob.id.in_(job_ids))
        else:
            conditions.append(KnowledgeIndexJob.status == scope)
        rows = (
            await db.execute(
                select(KnowledgeIndexJob)
                .where(*conditions)
                .order_by(KnowledgeIndexJob.create_time.desc())
                .limit(max(1, min(limit, 1000)))
            )
        ).scalars().all()
        seen: set[tuple] = set()
        for job in rows:
            key = (job.source_type, job.source_id, job.operation)
            if key in seen or job.source_id is None:
                continue
            seen.add(key)
            try:
                async with db.begin_nested():
                    db.add(
                        KnowledgeIndexJob(
                            source_type=job.source_type,
                            source_id=job.source_id,
                            operation=job.operation,
                            status="pending",
                            content_hash=job.content_hash,
                            pipeline_version=tag,
                            priority=10 if job.operation == "upsert" else 20,
                            max_attempts=3,
                            created_by=operator_id,
                            trace_id=f"reset-by:{operator}",
                        )
                    )
                    await db.flush()
                reset += 1
            except DETERMINISTIC_DB_ERRORS:
                logger.warning("reset raced for job %s; skipped", job.id)
        await db.commit()
    logger.info("admin reset: operator=%s reset=%s scope=%s", operator, reset, scope)
    return {"reset": reset}
