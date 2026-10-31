"""夜间向量索引调度服务的集成回归测试。

覆盖用户指定的回归面：
- 旧式软删除唯一键冲突（chunk 内容变化后重建不冲突）
- 同一内容第二次执行零 embedding 调用（hash 跳过）
- failed 任务退避不被 reconcile 清除/重置
- 单产品写库失败不回滚其他产品（savepoint 隔离）
- 活动（pending/processing）任务唯一索引防重复入队
- dead 隔离：hash/管线/模型不变不重开；变化或管理员重置才重开
- 启停行为：停用后不处理任务
- run-now 200 产品硬上限
- dead 90 天清理截止条件
- 僵死锁回收保留失败计数
- 报告/错误信息脱敏
- 单例 advisory lock 互斥

注意：跨会话读取的对象属性要提前取值（expire_on_commit 语义），
涉及唯一索引的夹具必须遵守"同一产品+操作至多一个未终态任务"。
"""

from __future__ import annotations

import asyncio
import uuid as uuid_mod
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

import app.core.database as core_db
import app.services.knowledge_index_scheduler as sched
from app.adapters.exceptions import AIAdapterError, AIAdapterRateLimitError
from app.knowledge.documents.base import KnowledgeDocumentUpserter
from app.knowledge.documents.product_card import DatabaseProductFactProvider
from app.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndexJob,
)
from app.models.product import Brand, Category, Product, Supplier


class FakeAdapter:
    """记录调用次数的假 embedding 适配器。"""

    def __init__(self, *, dim: int = 2048, fail: Exception | None = None):
        self.calls: list[list[str]] = []
        self.dim = dim
        self.fail = fail

    async def embed_with_usage(self, texts):
        self.calls.append(list(texts))
        if self.fail is not None:
            raise self.fail
        return [[0.5] * self.dim for _ in texts], {
            "prompt_tokens": 10 * len(texts),
            "total_tokens": 10 * len(texts),
            "source": "provider",
        }

    async def embed(self, texts):
        return (await self.embed_with_usage(texts))[0]


@pytest.fixture
async def ki_env(_engine, _sessionmaker, monkeypatch):
    """把调度服务的会话/引擎/适配器全部指向当前测试库与假适配器。"""
    monkeypatch.setattr(sched, "AsyncSessionLocal", _sessionmaker)
    monkeypatch.setattr(core_db, "engine", _engine)
    fake = FakeAdapter()
    monkeypatch.setattr(sched, "get_ai_adapter", lambda: fake)
    return SimpleNamespace(fake=fake, sessionmaker=_sessionmaker, engine=_engine)


@pytest.fixture
async def ki_setting(db):
    """取迁移种子出的单例配置行并加速（无请求间隔）。"""
    from app.models.knowledge_index_admin import SETTING_SINGLETON_ID

    row = await db.get(sched.KnowledgeIndexSetting, uuid_mod.UUID(SETTING_SINGLETON_ID))
    row.request_interval_seconds = 0
    row.reconcile_batch_size = 500
    row.embedding_batch_size = 48
    row.stale_lock_minutes = 15
    row.dead_retention_days = 90
    await db.commit()
    return row


async def _create_product(
    db, *, name: str, description: str = "适用于标准办公位。", commit: bool = True
) -> Product:
    brand = Brand(brand_name=f"brand-{uuid_mod.uuid4().hex[:8]}")
    category = Category(category_name=f"cat-{uuid_mod.uuid4().hex[:8]}", level=1, sort=0)
    supplier = Supplier(
        supplier_name=f"sup-{uuid_mod.uuid4().hex[:8]}",
        cooperation_status="active",
    )
    product = Product(
        product_no=f"P-{uuid_mod.uuid4().hex[:10]}",
        product_name=name,
        brand=brand,
        supplier=supplier,
        category=category,
        face_price=1999,
        cost_price=888,
        material="网布",
        stock_status="unknown",
        status="active",
        description=description,
        specification="680x680x980mm",
        colors="黑色/灰色",
        completeness_status="complete",
    )
    db.add_all([brand, category, supplier, product])
    await db.flush()
    if commit:
        await db.commit()
    return product


async def _add_job(db, product_or_id, *, status: str = "pending", **kwargs):
    source_id = getattr(product_or_id, "id", product_or_id)
    kwargs.setdefault("pipeline_version", sched.CARD_PIPELINE_VERSION)
    job = KnowledgeIndexJob(
        source_type="product_card",
        source_id=source_id,
        operation="upsert",
        status=status,
        **kwargs,
    )
    db.add(job)
    await db.flush()
    return job


async def _count_jobs(db, product_id, status: str | None = None) -> int:
    stmt = select(func.count()).select_from(KnowledgeIndexJob).where(
        KnowledgeIndexJob.source_type == "product_card",
        KnowledgeIndexJob.source_id == product_id,
        KnowledgeIndexJob.is_deleted.is_(False),
    )
    if status is not None:
        stmt = stmt.where(KnowledgeIndexJob.status == status)
    return int((await db.execute(stmt)).scalar() or 0)


# ---------------------------------------------------------------------------
# 1. reconcile 不重置 failed 退避
# ---------------------------------------------------------------------------


async def test_reconcile_does_not_reset_failed_backoff(db, ki_env, ki_setting):
    product = await _create_product(db, name="退避保护椅")
    pid = product.id
    backoff_until = datetime.now(UTC) + timedelta(hours=1)
    job = await _add_job(
        db,
        pid,
        status="failed",
        attempt_count=2,
        max_attempts=3,
        next_attempt_at=backoff_until,
        error_code="INDEX_UPSERT_FAILED",
        error_message="boom",
    )
    job_id = job.id
    await db.commit()

    result = await sched.reconcile_once(batch_size=100)

    assert result["queued"] >= 0
    db.expire_all()
    fresh = await db.get(KnowledgeIndexJob, job_id)
    # failed 任务原样保留：不被重置为 pending、不清空退避、不重置失败次数
    assert fresh.status == "failed"
    assert fresh.attempt_count == 2
    assert fresh.next_attempt_at is not None
    assert abs((fresh.next_attempt_at - backoff_until).total_seconds()) < 5
    # 也不会产生新的 pending 任务
    assert await _count_jobs(db, pid, "pending") == 0


async def test_failed_job_with_future_backoff_not_claimed(db, ki_env, ki_setting):
    product = await _create_product(db, name="未到期任务椅")
    pid = product.id
    await _add_job(
        db,
        pid,
        status="failed",
        attempt_count=1,
        max_attempts=3,
        next_attempt_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    await db.commit()

    async with ki_env.sessionmaker() as s:
        jobs = await sched._claim_card_jobs(s, limit=10, source_ids=None)  # noqa: SLF001
    assert jobs == []


# ---------------------------------------------------------------------------
# 2. 活动 pending 任务唯一索引
# ---------------------------------------------------------------------------


async def test_unique_active_job_index_blocks_duplicate_pending(db, ki_env, ki_setting):
    product = await _create_product(db, name="唯一索引椅")
    pid = product.id
    await _add_job(db, pid, status="pending")
    await db.commit()

    # 同组第二条未终态任务必须被数据库约束拒绝（先在 flush 处抛出）
    with pytest.raises(IntegrityError):
        await _add_job(db, pid, status="pending")
    await db.rollback()

    # 再验证约束在 commit 期（autoflush）同样生效
    db.add(
        KnowledgeIndexJob(
            source_type="product_card",
            source_id=pid,
            operation="upsert",
            status="pending",
            pipeline_version=sched.CARD_PIPELINE_VERSION,
        )
    )
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ---------------------------------------------------------------------------
# 3. dead 隔离：hash 不变不重开；变化/重置才重开
# ---------------------------------------------------------------------------


async def test_dead_quarantine_blocks_reconcile_until_hash_changes(db, ki_env, ki_setting):
    product = await _create_product(db, name="隔离椅")
    pid = product.id
    _model, _version, tag = sched.current_embedding_config()
    async with ki_env.sessionmaker() as s:
        payload = await DatabaseProductFactProvider(s).build_product_card(pid)
        await _add_job(
            s,
            pid,
            status="dead",
            content_hash=payload.content_hash,
            pipeline_version=tag,
            error_code=sched.DETERMINISTIC_ERROR_CODE,
            attempt_count=3,
            max_attempts=3,
        )
        await s.commit()

    result = await sched.reconcile_once(batch_size=100)
    assert result["blocked_dead"] >= 1
    async with ki_env.sessionmaker() as s:
        assert await _count_jobs(s, pid, "pending") == 0

    # 内容变化 → 允许重开
    async with ki_env.sessionmaker() as s:
        db_product = await s.get(Product, pid)
        db_product.description = "内容更新后的描述"
        await s.commit()
    result2 = await sched.reconcile_once(batch_size=100)
    assert result2["queued"] >= 1
    async with ki_env.sessionmaker() as s:
        assert await _count_jobs(s, pid, "pending") == 1


async def test_admin_reset_reopens_dead_job(db, ki_env, ki_setting):
    product = await _create_product(db, name="管理员重置椅")
    pid = product.id
    async with ki_env.sessionmaker() as s:
        await _add_job(
            s,
            pid,
            status="dead",
            error_code=sched.DETERMINISTIC_ERROR_CODE,
            attempt_count=3,
            max_attempts=3,
        )
        await s.commit()

    result = await sched.admin_reset_jobs(scope="dead", operator="test-admin")
    assert result["reset"] == 1
    async with ki_env.sessionmaker() as s:
        assert await _count_jobs(s, pid, "pending") == 1


# ---------------------------------------------------------------------------
# 4. hash 跳过：同一内容第二次执行零 embedding 调用
# ---------------------------------------------------------------------------


async def test_second_run_same_content_zero_embedding_calls(db, ki_env, ki_setting):
    product = await _create_product(db, name="零调用椅")
    pid = product.id

    # 第一轮：真正调用 embedding
    async with ki_env.sessionmaker() as s:
        await _add_job(s, pid, status="pending")
        await s.commit()
    outcome1 = await sched.process_product_card_batch(
        setting=ki_setting, allow_embedding=True
    )
    assert outcome1.counters.embedding_success == 1
    assert len(ki_env.fake.calls) == 1

    # 模拟队列残留：同内容再入队一次
    async with ki_env.sessionmaker() as s:
        await _add_job(s, pid, status="pending")
        await s.commit()
    outcome2 = await sched.process_product_card_batch(
        setting=ki_setting, allow_embedding=True
    )
    assert outcome2.counters.hash_skipped == 1
    assert outcome2.counters.embedding_success == 0
    # 关键断言：第二次没有发生任何外部 API 调用
    assert len(ki_env.fake.calls) == 1


# ---------------------------------------------------------------------------
# 5. 旧式软删除唯一键冲突回归
# ---------------------------------------------------------------------------


async def test_soft_deleted_chunk_rebuild_no_unique_conflict(db, ki_env, ki_setting):
    product = await _create_product(db, name="软删冲突椅")
    pid = product.id
    model, version, _tag = sched.current_embedding_config()

    async with ki_env.sessionmaker() as s:
        payload = await DatabaseProductFactProvider(s).build_product_card(pid)
        chunk = payload.chunks[0].finalized()
        chunk.embedding = [0.5] * 2048
        chunk.embedding_model = model
        chunk.embedding_version = version
        payload.chunks = [chunk]
        doc = await KnowledgeDocumentUpserter(s).upsert(payload)
        await s.commit()
        doc_id = doc.id

    # 内容变化后重建：旧行软删 + 新行插入，不得触发 (document_id, chunk_index) 冲突
    async with ki_env.sessionmaker() as s:
        db_product = await s.get(Product, pid)
        db_product.description = "变化后的内容 B"
        payload2 = await DatabaseProductFactProvider(s).build_product_card(pid)
        chunk2 = payload2.chunks[0].finalized()
        chunk2.embedding = [0.6] * 2048
        chunk2.embedding_model = model
        chunk2.embedding_version = version
        payload2.chunks = [chunk2]
        await KnowledgeDocumentUpserter(s).upsert(payload2)
        await s.commit()

        active = (
            await s.execute(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(
                    KnowledgeChunk.document_id == doc_id,
                    KnowledgeChunk.is_deleted.is_(False),
                )
            )
        ).scalar()
        deleted = (
            await s.execute(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(
                    KnowledgeChunk.document_id == doc_id,
                    KnowledgeChunk.is_deleted.is_(True),
                )
            )
        ).scalar()
        assert active == 1
        assert deleted == 1

    # 内容改回 A：同位软删历史行 + 新活动行共存（部分唯一索引语义）
    async with ki_env.sessionmaker() as s:
        db_product = await s.get(Product, pid)
        db_product.description = "适用于标准办公位。"
        payload3 = await DatabaseProductFactProvider(s).build_product_card(pid)
        chunk3 = payload3.chunks[0].finalized()
        chunk3.embedding = [0.7] * 2048
        chunk3.embedding_model = model
        chunk3.embedding_version = version
        payload3.chunks = [chunk3]
        await KnowledgeDocumentUpserter(s).upsert(payload3)
        await s.commit()  # 不抛 IntegrityError 即通过


# ---------------------------------------------------------------------------
# 6. 单产品写库失败不回滚其他产品
# ---------------------------------------------------------------------------


async def test_single_product_write_failure_isolated(db, ki_env, ki_setting, monkeypatch):
    product_a = await _create_product(db, name="正常产品A")
    poison_name = f"毒产品B-{uuid_mod.uuid4().hex[:6]}"
    product_b = await _create_product(db, name=poison_name)
    pid_a, pid_b = product_a.id, product_b.id

    real_upserter = sched.KnowledgeDocumentUpserter

    class PoisonUpserter(real_upserter):
        async def upsert(self, payload):
            if payload.source_id == pid_b:
                raise IntegrityError(
                    "INSERT", {}, Exception("simulated duplicate key on chunk")
                )
            return await super().upsert(payload)

    monkeypatch.setattr(sched, "KnowledgeDocumentUpserter", PoisonUpserter)

    async with ki_env.sessionmaker() as s:
        await _add_job(s, pid_a, status="pending")
        await _add_job(s, pid_b, status="pending")
        await s.commit()

    outcome = await sched.process_product_card_batch(
        setting=ki_setting, allow_embedding=True
    )
    assert outcome.counters.embedding_success == 1
    assert outcome.counters.quarantined == 1

    async with ki_env.sessionmaker() as s:
        doc_a = (
            await s.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.source_type == "product_card",
                    KnowledgeDocument.source_id == pid_a,
                    KnowledgeDocument.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        assert doc_a is not None and doc_a.index_status == "indexed"
        prod_a = await s.get(Product, pid_a)
        assert prod_a.vector is not None

        job_b = (
            await s.execute(
                select(KnowledgeIndexJob).where(
                    KnowledgeIndexJob.source_id == pid_b,
                    KnowledgeIndexJob.status == "dead",
                )
            )
        ).scalar_one()
        assert job_b.error_code == sched.DETERMINISTIC_ERROR_CODE
        doc_b = (
            await s.execute(
                select(func.count())
                .select_from(KnowledgeDocument)
                .where(KnowledgeDocument.source_id == pid_b)
            )
        ).scalar()
        assert doc_b == 0


# ---------------------------------------------------------------------------
# 7. 启停行为
# ---------------------------------------------------------------------------


async def _window_plan() -> sched.WindowPlan:
    now = datetime.now(UTC)
    return sched.WindowPlan(
        start_utc=now - timedelta(minutes=1),
        end_utc=now + timedelta(minutes=30),
        cutoff_utc=now + timedelta(minutes=15),
        next_start_utc=now + timedelta(days=1),
        active=True,
    )


async def test_disabled_service_processes_nothing(db, ki_env, ki_setting):
    product = await _create_product(db, name="停用椅")
    pid = product.id
    ki_setting.enabled = False
    await db.commit()

    async with ki_env.sessionmaker() as s:
        await _add_job(s, pid, status="pending")
        await s.commit()

    scheduler = sched.KnowledgeIndexScheduler()
    result = await scheduler._execute_run(  # noqa: SLF001
        trigger="scheduled",
        operator="system",
        operator_id=None,
        setting=ki_setting,
        plan=await _window_plan(),
    )
    assert result["status"] == "stopped"
    async with ki_env.sessionmaker() as s:
        assert await _count_jobs(s, pid, "pending") == 1
        assert await _count_jobs(s, pid, "succeeded") == 0
        assert len(ki_env.fake.calls) == 0


# ---------------------------------------------------------------------------
# 8. run-now 200 产品硬上限
# ---------------------------------------------------------------------------


async def test_run_now_product_cap_enforced(db, ki_env, ki_setting):
    for i in range(210):
        product = await _create_product(db, name=f"上限椅{i:03d}")
        await _add_job(db, product.id, status="pending")
    await db.commit()

    scheduler = sched.KnowledgeIndexScheduler()
    result = await scheduler._execute_run(  # noqa: SLF001
        trigger="run_now",
        operator="test-admin",
        operator_id=None,
        setting=ki_setting,
        plan=None,
        product_cap=sched.RUN_NOW_HARD_CAP,
    )
    assert result["stop_reason"] == "product_cap"

    async with ki_env.sessionmaker() as s:
        succeeded = (
            await s.execute(
                select(func.count())
                .select_from(KnowledgeIndexJob)
                .where(
                    KnowledgeIndexJob.status == "succeeded",
                    KnowledgeIndexJob.is_deleted.is_(False),
                )
            )
        ).scalar()
        still_pending = (
            await s.execute(
                select(func.count())
                .select_from(KnowledgeIndexJob)
                .where(
                    KnowledgeIndexJob.status == "pending",
                    KnowledgeIndexJob.is_deleted.is_(False),
                )
            )
        ).scalar()
    assert succeeded == 200  # 后端硬上限：绝不多做
    assert still_pending == 10
    assert len(ki_env.fake.calls) <= 200  # 每个产品至多一次 embedding


# ---------------------------------------------------------------------------
# 9. dead 90 天清理截止条件
# ---------------------------------------------------------------------------


async def test_dead_purge_only_expired(db, ki_env, ki_setting):
    now = datetime.now(UTC)
    p_old = await _create_product(db, name="清理椅旧")
    p_fresh = await _create_product(db, name="清理椅新")
    p_boundary = await _create_product(db, name="清理椅边界")
    p_pending = await _create_product(db, name="清理椅待处理")
    p_processing = await _create_product(db, name="清理椅处理中")
    await _add_job(db, p_old.id, status="dead", completed_at=now - timedelta(days=91))
    await _add_job(db, p_boundary.id, status="dead", completed_at=now - timedelta(days=90, hours=1))
    await _add_job(db, p_fresh.id, status="dead", completed_at=now - timedelta(days=89))
    await _add_job(db, p_pending.id, status="pending")
    await _add_job(db, p_processing.id, status="processing")
    await db.commit()

    purged = await sched.purge_dead_jobs(retention_days=90)
    assert purged == 2  # 91 天 + 90 天过线 1 小时；89 天保留

    async with ki_env.sessionmaker() as s:
        assert await _count_jobs(s, p_old.id, "dead") == 0
        assert await _count_jobs(s, p_boundary.id, "dead") == 0
        assert await _count_jobs(s, p_fresh.id, "dead") == 1  # 未过期保留
        assert await _count_jobs(s, p_pending.id, "pending") == 1  # 非 dead 绝不清理
        assert await _count_jobs(s, p_processing.id, "processing") == 1


# ---------------------------------------------------------------------------
# 10. 僵死锁回收（保留失败计数）
# ---------------------------------------------------------------------------


async def test_stale_processing_job_reclaimed(db, ki_env, ki_setting):
    p_fresh = await _create_product(db, name="新鲜锁椅")
    p_stale = await _create_product(db, name="僵死锁椅")
    fresh = await _add_job(
        db,
        p_fresh.id,
        status="processing",
        locked_by="old-worker",
        heartbeat_at=datetime.now(UTC),
        attempt_count=1,
    )
    stale = await _add_job(
        db,
        p_stale.id,
        status="processing",
        locked_by="dead-worker",
        heartbeat_at=datetime.now(UTC) - timedelta(minutes=30),
        attempt_count=2,
    )
    fresh_id, stale_id = fresh.id, stale.id
    await db.commit()

    await sched.reconcile_once(batch_size=100)

    db.expire_all()
    fresh_after = await db.get(KnowledgeIndexJob, fresh_id)
    stale_after = await db.get(KnowledgeIndexJob, stale_id)
    assert fresh_after.status == "processing"  # 心跳新鲜，不动
    assert stale_after.status == "pending"  # 僵死回收
    assert stale_after.attempt_count == 2  # 失败计数保留
    assert stale_after.locked_by is None


# ---------------------------------------------------------------------------
# 11. 报告/错误脱敏
# ---------------------------------------------------------------------------


async def test_error_message_sanitized_on_failure(db, ki_env, ki_setting, monkeypatch):
    product = await _create_product(db, name="脱敏椅")
    pid = product.id
    secret = "sk-live-abcdef123456"
    monkeypatch.setattr(
        sched,
        "get_ai_adapter",
        lambda: FakeAdapter(fail=AIAdapterError(f"upstream 401 with {secret}")),
    )
    async with ki_env.sessionmaker() as s:
        await _add_job(s, pid, status="pending")
        await s.commit()

    await sched.process_product_card_batch(setting=ki_setting, allow_embedding=True)

    async with ki_env.sessionmaker() as s:
        job = (
            await s.execute(
                select(KnowledgeIndexJob).where(KnowledgeIndexJob.source_id == pid)
            )
        ).scalar_one()
    assert secret not in (job.error_message or "")
    assert job.status == "failed"


# ---------------------------------------------------------------------------
# 12. 单例 advisory lock 互斥
# ---------------------------------------------------------------------------


async def test_singleton_lock_mutual_exclusion(ki_env):
    lock1 = sched.SingletonLock()
    lock2 = sched.SingletonLock()
    assert await lock1.acquire() is True
    try:
        assert await lock2.acquire() is False
        assert lock2.acquired is False
    finally:
        await lock1.release()
    assert await lock2.acquire() is True
    await lock2.release()


# ---------------------------------------------------------------------------
# 13. 计划窗口去重（同一窗口只跑一次）
# ---------------------------------------------------------------------------


async def test_scheduled_run_dedup(db, ki_env, ki_setting):
    plan = await _window_plan()
    async with ki_env.sessionmaker() as s:
        s.add(
            sched.KnowledgeIndexRun(
                trigger_type="scheduled",
                operator="system",
                status="completed",
                started_at=datetime.now(UTC),
                window_start_at=plan.start_utc,
            )
        )
        await s.commit()
    assert await sched._scheduled_run_exists(plan) is True  # noqa: SLF001

    plan2 = await _window_plan()
    assert plan2.start_utc != plan.start_utc
    assert await sched._scheduled_run_exists(plan2) is False  # noqa: SLF001


# ---------------------------------------------------------------------------
# 14. token 用量记录（实测优先）
# ---------------------------------------------------------------------------


async def test_token_usage_recorded_in_run_report(db, ki_env, ki_setting):
    product = await _create_product(db, name="用量椅")
    pid = product.id
    async with ki_env.sessionmaker() as s:
        await _add_job(s, pid, status="pending")
        await s.commit()

    scheduler = sched.KnowledgeIndexScheduler()
    result = await scheduler._execute_run(  # noqa: SLF001
        trigger="run_now",
        operator="test",
        operator_id=None,
        setting=ki_setting,
        plan=None,
        product_cap=200,
    )
    assert result["status"] in ("completed", "stopped")

    async with ki_env.sessionmaker() as s:
        run = (
            await s.execute(
                select(sched.KnowledgeIndexRun).order_by(
                    sched.KnowledgeIndexRun.started_at.desc()
                )
            )
        ).scalars().first()
    assert run is not None
    assert (run.token_usage_actual or 0) == 10  # FakeAdapter 每文本 10 tokens
    assert run.token_usage_estimated is None  # 有实测时不得写估算
    assert run.details.get("token_usage_source") == "provider"


# ---------------------------------------------------------------------------
# 15. 审查修复回归：run-now_sync 硬上限 / advisory lock / 停用拒绝
# ---------------------------------------------------------------------------


async def test_run_now_sync_hard_cap_ignores_reconcile_batch_size(db, ki_env, ki_setting):
    """CLI/同步入口的产品上限固定 200，不受 reconcile_batch_size 影响。"""
    for i in range(210):
        product = await _create_product(db, name=f"同步上限椅{i:03d}")
        await _add_job(db, product.id, status="pending")
    await db.commit()
    ki_setting.reconcile_batch_size = 5  # 故意调小，验证不能借此放大上限
    await db.commit()

    result = await sched.KnowledgeIndexScheduler().run_now_sync(operator="cli-test")
    assert result["status"] in ("completed", "stopped")

    async with ki_env.sessionmaker() as s:
        succeeded = (
            await s.execute(
                select(func.count())
                .select_from(KnowledgeIndexJob)
                .where(KnowledgeIndexJob.status == "succeeded")
            )
        ).scalar()
    assert succeeded == 200  # 恰好 200，多一个都不行


async def test_run_now_sync_busy_when_advisory_lock_held(db, ki_env, ki_setting):
    """跨进程互斥：advisory lock 被占（模拟另一进程/夜间窗口）时拒绝。"""
    lock = sched.SingletonLock()
    assert await lock.acquire() is True
    try:
        with pytest.raises(sched.SchedulerBusyError):
            await sched.KnowledgeIndexScheduler().run_now_sync(operator="cli-test")
        assert len(ki_env.fake.calls) == 0
    finally:
        await lock.release()


async def test_run_now_sync_rejected_when_disabled(db, ki_env, ki_setting):
    ki_setting.enabled = False
    await db.commit()
    with pytest.raises(sched.SchedulerDisabledError):
        await sched.KnowledgeIndexScheduler().run_now_sync(operator="cli-test")


async def test_cli_once_module_reuses_run_now_constraints(db, ki_env, ki_setting, monkeypatch):
    """CLI --once 语义：占用单例锁时必须报忙（asyncio.Lock 误用回归）。"""
    from app.scripts import knowledge_indexer as cli

    lock = sched.SingletonLock()
    assert await lock.acquire() is True
    try:
        with pytest.raises(sched.SchedulerBusyError):
            await cli._run_once()
    finally:
        await lock.release()


# ---------------------------------------------------------------------------
# 16. 审查修复回归：批量失败必须递增 attempt_count 并最终进入 dead
# ---------------------------------------------------------------------------


async def test_batch_failure_increments_attempt_until_dead(db, ki_env, ki_setting, monkeypatch):
    product = await _create_product(db, name="退避递增椅")
    pid = product.id
    async with ki_env.sessionmaker() as s:
        await _add_job(s, pid, status="pending")
        await s.commit()

    monkeypatch.setattr(
        sched,
        "get_ai_adapter",
        lambda: FakeAdapter(fail=AIAdapterError("upstream 500 exploded")),
    )

    for expected_attempt in (1, 2, 3):
        outcome = await sched.process_product_card_batch(
            setting=ki_setting, allow_embedding=True
        )
        assert outcome.counters.failed == 1
        # 把退避时间拨回过去，模拟退避到期后的下一次尝试
        async with ki_env.sessionmaker() as s:
            job = (
                await s.execute(
                    select(KnowledgeIndexJob).where(KnowledgeIndexJob.source_id == pid)
                )
            ).scalar_one()
            job.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await s.commit()
        async with ki_env.sessionmaker() as s:
            job = (
                await s.execute(
                    select(KnowledgeIndexJob).where(KnowledgeIndexJob.source_id == pid)
                )
            ).scalar_one()
            assert job.attempt_count == expected_attempt
            if expected_attempt < 3:
                assert job.status == "failed"
            else:
                assert job.status == "dead"  # 3 次后进入 dead，不再每晚重试


async def test_rate_limit_failure_does_not_consume_attempt(db, ki_env, ki_setting, monkeypatch):
    product = await _create_product(db, name="限流不计数椅")
    pid = product.id
    async with ki_env.sessionmaker() as s:
        await _add_job(s, pid, status="pending")
        await s.commit()

    monkeypatch.setattr(
        sched,
        "get_ai_adapter",
        lambda: FakeAdapter(fail=AIAdapterRateLimitError("429 slow down")),
    )
    outcome = await sched.process_product_card_batch(setting=ki_setting, allow_embedding=True)
    assert outcome.counters.rate_limited == 1
    async with ki_env.sessionmaker() as s:
        job = (
            await s.execute(
                select(KnowledgeIndexJob).where(KnowledgeIndexJob.source_id == pid)
            )
        ).scalar_one()
    assert job.status == "failed"
    assert job.attempt_count == 0  # 429 不消耗重试预算
    assert job.error_code == "INDEX_RATE_LIMITED"


# ---------------------------------------------------------------------------
# 17. 审查修复回归：同产品多个 failed 任务只请求一次
# ---------------------------------------------------------------------------


async def test_multiple_failed_jobs_same_product_embedded_once(db, ki_env, ki_setting):
    product = await _create_product(db, name="多失败历史椅")
    pid = product.id
    async with ki_env.sessionmaker() as s:
        await _add_job(
            s, pid, status="failed", attempt_count=1, max_attempts=3,
            next_attempt_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        await _add_job(
            s, pid, status="failed", attempt_count=1, max_attempts=3,
            next_attempt_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        await s.commit()

    outcome = await sched.process_product_card_batch(setting=ki_setting, allow_embedding=True)

    # 单次 embedding 请求只包含一个产品的一条任务
    assert len(ki_env.fake.calls) == 1
    assert len(ki_env.fake.calls[0]) == 1
    assert outcome.counters.embedding_success == 1
    async with ki_env.sessionmaker() as s:
        # 两条历史 failed 的 create_time 相同（同事务 now()），按状态断言：
        # 恰好一条被处理成功，另一条作为历史保留、绝不再发请求。
        succeeded = (
            await s.execute(
                select(func.count())
                .select_from(KnowledgeIndexJob)
                .where(KnowledgeIndexJob.source_id == pid, KnowledgeIndexJob.status == "succeeded")
            )
        ).scalar()
        failed = (
            await s.execute(
                select(func.count())
                .select_from(KnowledgeIndexJob)
                .where(KnowledgeIndexJob.source_id == pid, KnowledgeIndexJob.status == "failed")
            )
        ).scalar()
    assert succeeded == 1
    assert failed == 1


# ---------------------------------------------------------------------------
# 18. 审查修复回归：业务 enqueue 不清除 failed 退避（dispatcher）
# ---------------------------------------------------------------------------


async def test_business_enqueue_preserves_failed_backoff(db, ki_env, ki_setting):
    from app.knowledge.jobs.dispatcher import KnowledgeJobDispatcher

    product = await _create_product(db, name="编辑不清退避椅")
    pid = product.id
    backoff_until = datetime.now(UTC) + timedelta(hours=1)
    async with ki_env.sessionmaker() as s:
        old = await _add_job(
            s, pid, status="failed", attempt_count=2, max_attempts=3,
            next_attempt_at=backoff_until, error_code="INDEX_UPSERT_FAILED",
        )
        old_id = old.id
        await s.commit()

        await KnowledgeJobDispatcher(s).enqueue_job(
            source_type="product_card", source_id=pid, operation="upsert"
        )
        await s.commit()

        s.expire_all()
        preserved = await s.get(KnowledgeIndexJob, old_id)
        # 原 failed 任务原样保留：退避、失败计数、错误信息都不被清除
        assert preserved.status == "failed"
        assert preserved.attempt_count == 2
        assert preserved.error_code == "INDEX_UPSERT_FAILED"
        assert abs((preserved.next_attempt_at - backoff_until).total_seconds()) < 5
        # 新建了一条 pending 任务承接本次内容变更
        pendings = (
            await s.execute(
                select(KnowledgeIndexJob).where(
                    KnowledgeIndexJob.source_id == pid,
                    KnowledgeIndexJob.status == "pending",
                )
            )
        ).scalars().all()
        assert len(pendings) == 1


async def test_business_enqueue_does_not_hijack_processing(db, ki_env, ki_setting):
    from app.knowledge.jobs.dispatcher import KnowledgeJobDispatcher

    product = await _create_product(db, name="飞行不劫持椅")
    pid = product.id
    async with ki_env.sessionmaker() as s:
        job = await _add_job(
            s, pid, status="processing", locked_by="worker-1",
            heartbeat_at=datetime.now(UTC),
        )
        job_id = job.id
        await s.commit()

        returned = await KnowledgeJobDispatcher(s).enqueue_job(
            source_type="product_card", source_id=pid, operation="upsert"
        )
        await s.commit()
        s.expire_all()
        fresh = await s.get(KnowledgeIndexJob, job_id)
        assert fresh.id == returned.id
        assert fresh.status == "processing"  # 飞行中任务不被重置
        assert fresh.locked_by == "worker-1"
        assert await _count_jobs(s, pid, "pending") == 0


# ---------------------------------------------------------------------------
# 19. 审查修复回归：knowledge_document 活动唯一约束
# ---------------------------------------------------------------------------


async def test_active_document_unique_index_blocks_duplicate(db, ki_env, ki_setting):
    from uuid import uuid4 as new_uuid

    source_key = new_uuid()
    async with ki_env.sessionmaker() as s:
        s.add(
            KnowledgeDocument(
                source_type="product_card",
                source_id=source_key,
                title="first",
                doc_type="product_card",
                content_hash="h1",
            )
        )
        await s.commit()
        s.add(
            KnowledgeDocument(
                source_type="product_card",
                source_id=source_key,
                title="second",
                doc_type="product_card",
                content_hash="h2",
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()
        await s.rollback()

        # 软删历史行 + 新活动行共存不受约束影响
        first = (
            await s.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.source_id == source_key
                )
            )
        ).scalar_one()
        first.is_deleted = True
        first.deleted_at = datetime.now(UTC)
        await s.commit()
        s.add(
            KnowledgeDocument(
                source_type="product_card",
                source_id=source_key,
                title="third",
                doc_type="product_card",
                content_hash="h3",
            )
        )
        await s.commit()  # 不抛 IntegrityError 即通过


# ---------------------------------------------------------------------------
# 20. 审查修复回归：停机收尾与启动恢复
# ---------------------------------------------------------------------------


async def test_cancelled_run_finalizes_report_as_stopped(db, ki_env, ki_setting, monkeypatch):
    product = await _create_product(db, name="停机收尾椅")
    pid = product.id
    async with ki_env.sessionmaker() as s:
        await _add_job(s, pid, status="pending")
        await s.commit()

    async def cancelled_batch(**kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(sched, "process_product_card_batch", cancelled_batch)

    scheduler = sched.KnowledgeIndexScheduler()
    with pytest.raises(asyncio.CancelledError):
        await scheduler._execute_run(  # noqa: SLF001
            trigger="scheduled",
            operator="system",
            operator_id=None,
            setting=ki_setting,
            plan=await _window_plan(),
        )

    async with ki_env.sessionmaker() as s:
        run = (
            await s.execute(
                select(sched.KnowledgeIndexRun).order_by(
                    sched.KnowledgeIndexRun.started_at.desc()
                )
            )
        ).scalars().first()
        state = await s.get(sched.KnowledgeIndexSchedulerState,
                            uuid_mod.UUID("00000000-0000-0000-0000-000000000038"))
    assert run.status == "stopped"  # 报告不永久停留在 running
    assert run.finished_at is not None
    assert run.details["stop_reason"] == "stopping"
    assert state.current_run_id is None


async def test_startup_recovery_marks_stale_running_stopped(db, ki_env, ki_setting):
    from app.models.knowledge_index_admin import STATE_SINGLETON_ID

    stale_started = datetime.now(UTC) - timedelta(minutes=30)
    async with ki_env.sessionmaker() as s:
        run = sched.KnowledgeIndexRun(
            trigger_type="scheduled",
            operator="system",
            status="running",
            started_at=stale_started,
        )
        s.add(run)
        await s.flush()
        run_id = run.id
        state = await s.get(sched.KnowledgeIndexSchedulerState, uuid_mod.UUID(STATE_SINGLETON_ID))
        state.current_run_id = run_id
        await s.commit()

    fixed = await sched.recover_stale_running()
    assert fixed == 1

    async with ki_env.sessionmaker() as s:
        recovered = await s.get(sched.KnowledgeIndexRun, run_id)
        state = await s.get(sched.KnowledgeIndexSchedulerState, uuid_mod.UUID(STATE_SINGLETON_ID))
    assert recovered.status == "stopped"
    assert recovered.finished_at is not None
    assert state.current_run_id is None
