"""驾驶舱 API（HLD §8.4 / §11）。

5 个端点：overview / funnel / sales / todos / content。
- 所有聚合查询过 apply_data_scope（§6.4）
- 金额字段对 designer/operator 后端直接剔除
- Redis 缓存 45s（金额字段不进缓存，直查合并）
- 空态：value:null + empty_reason（禁止 0 占位）
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from datetime import UTC, datetime, timedelta

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.data_scope import _visible_customer_ids, apply_data_scope
from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.customer import Customer, FollowUp
from app.models.project import Project
from app.models.reminder import Reminder
from app.models.sales import Proposal, Quotation
from app.models.user import User

logger = logging.getLogger("app.dashboard")

router = APIRouter(prefix="/api/v1/stats/dashboard", tags=["dashboard"])

# ---------------------------------------------------------------------------
# 缓存（HLD §11.2）
# ---------------------------------------------------------------------------

_CACHE_TTL = 45  # 秒


async def _get_redis() -> redis.Redis | None:
    """获取 Redis 连接；不可用返回 None（fail-open，直查）。"""
    try:
        client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await client.ping()
        return client
    except Exception:
        return None


def _cache_key(endpoint: str, user_id: str, role_code: str, params: dict) -> str:
    raw = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return f"dash:{endpoint}:{user_id}:{role_code}:{digest}"


async def _cache_get_or_compute(
    key: str,
    compute_fn,
    ttl: int = _CACHE_TTL,
) -> tuple[dict, bool]:
    """缓存读取或计算。返回 (data, cached)。"""
    client = await _get_redis()
    if client is not None:
        try:
            raw = await client.get(key)
            if raw is not None:
                return json.loads(raw), True
        except Exception:
            pass

    # 计算（SETNX 短锁防击穿）
    lock_key = f"{key}:lock"
    locked = False
    if client is not None:
        try:
            locked = await client.set(lock_key, "1", nx=True, ex=5)
        except Exception:
            locked = False

    if locked:
        try:
            result = await compute_fn()
            jitter = random.randint(-5, 5)
            await client.set(key, json.dumps(result, default=str), ex=ttl + jitter)
            return result, False
        except Exception:
            raise
        finally:
            try:
                await client.delete(lock_key)
            except Exception:
                pass
    else:
        # 未拿到锁：短暂等待后重试缓存，否则直查
        if client is not None:
            await asyncio.sleep(0.1)
            try:
                raw = await client.get(key)
                if raw is not None:
                    return json.loads(raw), True
            except Exception:
                pass
        result = await compute_fn()
        return result, False


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _parse_range(range_str: str | None) -> tuple[datetime, datetime]:
    """解析 '30d'/'7d'/'90d'/'1w'/'1m' → (start, end)。默认 30d。"""
    if not range_str:
        range_str = "30d"
    range_str = range_str.strip().lower()
    now = datetime.now(UTC)
    try:
        if range_str.endswith("d"):
            days = int(range_str[:-1])
        elif range_str.endswith("w"):
            days = int(range_str[:-1]) * 7
        elif range_str.endswith("m"):
            days = int(range_str[:-1]) * 30
        else:
            days = 30
    except ValueError:
        days = 30
    if days <= 0:
        days = 30
    start = now - timedelta(days=days)
    return start, now


def _trend(value: int, prev: int) -> float | None:
    """环比趋势：(value - prev) / prev，保留 2 位小数。prev=0 → None。"""
    if prev == 0:
        return None
    return round((value - prev) / prev, 2)


def _amount_visible(role_code: str) -> bool:
    """金额字段可见角色：admin/manager/sales。"""
    return role_code in ("admin", "manager", "sales")


# ---------------------------------------------------------------------------
# GET /overview
# ---------------------------------------------------------------------------


@router.get("/overview", dependencies=[Depends(PermissionChecker("dashboard:view"))])
@audit_action("dashboard_overview", module="dashboard")
async def dashboard_overview(
    request: Request,
    range: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    start_dt, end_dt = _parse_range(range)
    prev_start = start_dt - (end_dt - start_dt)

    cache_key = _cache_key("overview", user_id, role_code, {"range": range})

    async def compute():
        return await _compute_overview(
            db, user_id, role_code, start_dt, end_dt, prev_start
        )

    data, cached = await _cache_get_or_compute(cache_key, compute)

    # 金额字段不进缓存，直查合并
    if _amount_visible(role_code):
        data["confirmed_amount"] = await _compute_confirmed_amount(
            db, user_id, role_code, start_dt, end_dt
        )
    else:
        data["confirmed_amount"] = {"visible": False}

    data["generated_at"] = datetime.now(UTC).isoformat()
    data["cached"] = cached
    return {"code": 200, "data": data}


async def _compute_overview(
    db: AsyncSession,
    user_id: str,
    role_code: str,
    start_dt: datetime,
    end_dt: datetime,
    prev_start: datetime,
) -> dict:
    now = datetime.now(UTC)

    # --- new_customers ---
    new_cust_stmt = select(func.count(Customer.id)).where(
        Customer.is_deleted.is_(False),
        Customer.create_time >= start_dt,
        Customer.create_time < end_dt,
    )
    new_cust_stmt = apply_data_scope(
        new_cust_stmt, user_id=user_id, role_code=role_code, model=Customer
    )
    new_cust = (await db.execute(new_cust_stmt)).scalar_one()

    prev_cust_stmt = select(func.count(Customer.id)).where(
        Customer.is_deleted.is_(False),
        Customer.create_time >= prev_start,
        Customer.create_time < start_dt,
    )
    prev_cust_stmt = apply_data_scope(
        prev_cust_stmt, user_id=user_id, role_code=role_code, model=Customer
    )
    prev_cust = (await db.execute(prev_cust_stmt)).scalar_one()

    # --- active_projects (created in range, status=active) ---
    new_proj_stmt = select(func.count(Project.id)).where(
        Project.is_deleted.is_(False),
        Project.status == "active",
        Project.create_time >= start_dt,
        Project.create_time < end_dt,
    )
    new_proj_stmt = apply_data_scope(
        new_proj_stmt, user_id=user_id, role_code=role_code, model=Project
    )
    new_proj = (await db.execute(new_proj_stmt)).scalar_one()

    prev_proj_stmt = select(func.count(Project.id)).where(
        Project.is_deleted.is_(False),
        Project.status == "active",
        Project.create_time >= prev_start,
        Project.create_time < start_dt,
    )
    prev_proj_stmt = apply_data_scope(
        prev_proj_stmt, user_id=user_id, role_code=role_code, model=Project
    )
    prev_proj = (await db.execute(prev_proj_stmt)).scalar_one()

    # --- overdue_follow_ups (point-in-time) ---
    overdue_stmt = select(func.count(FollowUp.id)).where(
        FollowUp.is_deleted.is_(False),
        FollowUp.done_at.is_(None),
        FollowUp.next_follow_at < now,
    )
    overdue_stmt = apply_data_scope(
        overdue_stmt, user_id=user_id, role_code=role_code, model=FollowUp
    )
    overdue = (await db.execute(overdue_stmt)).scalar_one()

    # prev: overdue at range start
    overdue_prev_stmt = select(func.count(FollowUp.id)).where(
        FollowUp.is_deleted.is_(False),
        FollowUp.done_at.is_(None),
        FollowUp.next_follow_at < start_dt,
    )
    overdue_prev_stmt = apply_data_scope(
        overdue_prev_stmt, user_id=user_id, role_code=role_code, model=FollowUp
    )
    overdue_prev = (await db.execute(overdue_prev_stmt)).scalar_one()

    # --- stalled_projects ---
    stall_threshold = now - timedelta(days=7)
    stalled_stmt = select(func.count(Project.id)).where(
        Project.is_deleted.is_(False),
        Project.status == "active",
        func.coalesce(Project.last_activity_at, Project.create_time) < stall_threshold,
    )
    stalled_stmt = apply_data_scope(
        stalled_stmt, user_id=user_id, role_code=role_code, model=Project
    )
    stalled = (await db.execute(stalled_stmt)).scalar_one()

    return {
        "range": {"from": start_dt.isoformat(), "to": end_dt.isoformat()},
        "new_customers": {
            "value": new_cust,
            "prev": prev_cust,
            "trend": _trend(new_cust, prev_cust),
        },
        "active_projects": {
            "value": new_proj,
            "prev": prev_proj,
            "trend": _trend(new_proj, prev_proj),
        },
        "overdue_follow_ups": {
            "value": overdue,
            "prev": overdue_prev,
            "trend": _trend(overdue, overdue_prev),
        },
        "stalled_projects": {
            "value": stalled,
            "threshold_days": 7,
        },
    }


async def _compute_confirmed_amount(
    db: AsyncSession,
    user_id: str,
    role_code: str,
    start_dt: datetime,
    end_dt: datetime,
) -> dict:
    """已确认金额：sum(quotation.total_amount WHERE status='confirmed')。

    按可见客户范围过滤（经 Proposal.customer_id）。
    """
    visible = _visible_customer_ids(user_id, role_code)

    # 先检查是否有 confirmed 报价
    count_stmt = (
        select(func.count(Quotation.id))
        .where(
            Quotation.is_deleted.is_(False),
            Quotation.status == "confirmed",
            Quotation.proposal_id.in_(
                select(Proposal.id).where(
                    Proposal.is_deleted.is_(False),
                    Proposal.customer_id.in_(visible),
                )
            ),
        )
    )
    count = (await db.execute(count_stmt)).scalar_one()
    if count == 0:
        return {"value": None, "empty_reason": "no_data", "currency": "CNY", "visible": True}

    stmt = (
        select(func.coalesce(func.sum(Quotation.total_amount), 0))
        .where(
            Quotation.is_deleted.is_(False),
            Quotation.status == "confirmed",
            Quotation.proposal_id.in_(
                select(Proposal.id).where(
                    Proposal.is_deleted.is_(False),
                    Proposal.customer_id.in_(visible),
                )
            ),
        )
    )
    amount = (await db.execute(stmt)).scalar_one()
    return {
        "value": round(amount, 2),
        "currency": "CNY",
        "visible": True,
    }


# ---------------------------------------------------------------------------
# GET /funnel
# ---------------------------------------------------------------------------


@router.get("/funnel", dependencies=[Depends(PermissionChecker("dashboard:view"))])
@audit_action("dashboard_funnel", module="dashboard")
async def dashboard_funnel(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    cache_key = _cache_key("funnel", user_id, role_code, {})

    async def compute():
        return await _compute_funnel(db, user_id, role_code)

    data, cached = await _cache_get_or_compute(cache_key, compute)
    data["cached"] = cached
    return {"code": 200, "data": data}


async def _compute_funnel(db: AsyncSession, user_id: str, role_code: str) -> dict:
    # 客户漏斗（0 补齐）
    cust_stages = ["lead", "contacted", "needs", "quoted", "won", "lost"]
    stmt = (
        select(Customer.stage, func.count(Customer.id))
        .where(Customer.is_deleted.is_(False))
        .group_by(Customer.stage)
    )
    stmt = apply_data_scope(stmt, user_id=user_id, role_code=role_code, model=Customer)
    rows = (await db.execute(stmt)).all()
    counts = {s: 0 for s in cust_stages}
    for stage, cnt in rows:
        if stage in counts:
            counts[stage] = cnt
    customer_funnel = [{"stage": s, "count": counts[s]} for s in cust_stages]

    # 项目阶段分布（status='active'）
    proj_stages = ["lead", "measuring", "design", "quoted", "producing", "delivered", "closed"]
    stmt = (
        select(Project.stage, func.count(Project.id))
        .where(
            Project.is_deleted.is_(False),
            Project.status == "active",
        )
        .group_by(Project.stage)
    )
    stmt = apply_data_scope(stmt, user_id=user_id, role_code=role_code, model=Project)
    rows = (await db.execute(stmt)).all()
    counts = {s: 0 for s in proj_stages}
    for stage, cnt in rows:
        if stage in counts:
            counts[stage] = cnt
    project_stages = [{"stage": s, "count": counts[s]} for s in proj_stages]

    return {
        "customer_funnel": customer_funnel,
        "project_stages": project_stages,
    }


# ---------------------------------------------------------------------------
# GET /sales
# ---------------------------------------------------------------------------


@router.get("/sales", dependencies=[Depends(PermissionChecker("dashboard:view"))])
@audit_action("dashboard_sales", module="dashboard")
async def dashboard_sales(
    request: Request,
    range: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    start_dt, end_dt = _parse_range(range)

    cache_key = _cache_key("sales", user_id, role_code, {"range": range})

    async def compute():
        return await _compute_sales_ranking(db, user_id, role_code, start_dt, end_dt)

    data, cached = await _cache_get_or_compute(cache_key, compute)

    # sales 仅 my_row
    if role_code == "sales":
        data["ranking"] = []

    data["cached"] = cached
    return {"code": 200, "data": data}


async def _compute_sales_ranking(
    db: AsyncSession,
    user_id: str,
    role_code: str,
    start_dt: datetime,
    end_dt: datetime,
) -> dict:
    """销售跟进排行：按 follower 统计 range 内跟进数。"""
    stmt = (
        select(User.id, User.username, func.count(FollowUp.id).label("cnt"))
        .join(FollowUp, FollowUp.follower_id == User.id)
        .where(
            FollowUp.is_deleted.is_(False),
            FollowUp.create_time >= start_dt,
            FollowUp.create_time < end_dt,
        )
        .group_by(User.id, User.username)
        .order_by(func.count(FollowUp.id).desc())
    )
    stmt = apply_data_scope(stmt, user_id=user_id, role_code=role_code, model=FollowUp)
    rows = (await db.execute(stmt)).all()

    ranking = []
    my_row = None
    for rank, (uid, username, cnt) in enumerate(rows, start=1):
        row = {
            "follower_id": str(uid),
            "name": username,
            "count": cnt,
            "rank": rank,
        }
        ranking.append(row)
        if str(uid) == str(user_id):
            my_row = row

    return {
        "ranking": ranking[:10],
        "my_row": my_row,
    }


# ---------------------------------------------------------------------------
# GET /todos
# ---------------------------------------------------------------------------


@router.get("/todos", dependencies=[Depends(PermissionChecker("dashboard:view"))])
@audit_action("dashboard_todos", module="dashboard")
async def dashboard_todos(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    cache_key = _cache_key("todos", user_id, role_code, {"limit": limit})

    async def compute():
        return await _compute_todos(db, user_id, role_code, limit)

    data, cached = await _cache_get_or_compute(cache_key, compute)
    data["cached"] = cached
    return {"code": 200, "data": data}


async def _compute_todos(
    db: AsyncSession,
    user_id: str,
    role_code: str,
    limit: int,
) -> dict:
    """我的待办：reminders ∪ follow_ups。"""
    # reminders
    rem_stmt = (
        select(Reminder)
        .where(
            Reminder.is_deleted.is_(False),
            Reminder.assignee_id == user_id,
            Reminder.status.in_(["pending", "sent", "overdue"]),
        )
        .order_by(Reminder.due_at.asc())
        .limit(limit)
    )
    rem_stmt = apply_data_scope(rem_stmt, user_id=user_id, role_code=role_code, model=Reminder)
    reminders = (await db.execute(rem_stmt)).scalars().all()

    # follow_ups
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    fu_stmt = (
        select(FollowUp)
        .where(
            FollowUp.is_deleted.is_(False),
            FollowUp.follower_id == user_id,
            FollowUp.done_at.is_(None),
            FollowUp.next_follow_at <= tomorrow,
        )
        .order_by(FollowUp.next_follow_at.asc())
        .limit(limit)
    )
    fu_stmt = apply_data_scope(fu_stmt, user_id=user_id, role_code=role_code, model=FollowUp)
    follow_ups = (await db.execute(fu_stmt)).scalars().all()

    # total_pending（精确计数，不受 limit 限制）
    rem_count_stmt = select(func.count(Reminder.id)).where(
        Reminder.is_deleted.is_(False),
        Reminder.assignee_id == user_id,
        Reminder.status.in_(["pending", "sent", "overdue"]),
    )
    rem_count_stmt = apply_data_scope(
        rem_count_stmt, user_id=user_id, role_code=role_code, model=Reminder
    )
    rem_total = (await db.execute(rem_count_stmt)).scalar_one()

    fu_count_stmt = select(func.count(FollowUp.id)).where(
        FollowUp.is_deleted.is_(False),
        FollowUp.follower_id == user_id,
        FollowUp.done_at.is_(None),
        FollowUp.next_follow_at <= tomorrow,
    )
    fu_count_stmt = apply_data_scope(
        fu_count_stmt, user_id=user_id, role_code=role_code, model=FollowUp
    )
    fu_total = (await db.execute(fu_count_stmt)).scalar_one()

    return {
        "reminders": [
            {
                "id": str(r.id),
                "title": r.title,
                "body": r.body,
                "due_at": r.due_at.isoformat() if r.due_at else None,
                "status": r.status,
                "rule_code": r.rule_code,
            }
            for r in reminders
        ],
        "follow_ups": [
            {
                "id": str(f.id),
                "customer_id": str(f.customer_id),
                "project_id": str(f.project_id) if f.project_id else None,
                "method": f.method,
                "content": f.content,
                "next_follow_at": f.next_follow_at.isoformat() if f.next_follow_at else None,
            }
            for f in follow_ups
        ],
        "total_pending": rem_total + fu_total,
    }


# ---------------------------------------------------------------------------
# GET /content
# ---------------------------------------------------------------------------


@router.get("/content", dependencies=[Depends(PermissionChecker("dashboard:view"))])
@audit_action("dashboard_content", module="dashboard")
async def dashboard_content(
    request: Request,
    range: str = Query("30d"),
):
    """Phase 3：内容卡返回 module_disabled（Phase 4 开启）。"""
    return {
        "code": 200,
        "data": {"empty": True, "empty_reason": "module_disabled"},
    }
