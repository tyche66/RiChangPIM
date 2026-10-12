"""客户域 API（HLD §8.3）。

实现客户 CRUD、阶段迁移、PII 查看、所有权转移、汇总、时间线、子资源等端点。
所有端点挂 PermissionChecker + apply_data_scope + assert_object_scope。
"""

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.data_scope import apply_data_scope, assert_object_scope
from app.core.database import get_db
from app.core.masking import mask_address, mask_phone, mask_wechat
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.customer import (
    Customer,
    CustomerDialogue,
    EntityStageLog,
    FollowUp,
    Requirement,
)
from app.models.project import Project
from app.models.reminder import Reminder
from app.models.sales import Proposal, Quotation
from app.models.user import User
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    StageTransitionRequest,
)
from app.services.customer_state import validate_transition

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

VALID_STAGES = {"lead", "contacted", "needs", "quoted", "won", "lost"}
VALID_LEVELS = {"A", "B", "C"}
VALID_SOURCES = {"new_media", "store", "referral", "exhibition", "other"}

# 金额字段可见角色（§6.4 / §11.1）
_AMOUNT_VISIBLE_ROLES = {"admin", "manager", "sales"}


def _normalize_phone(phone: str | None) -> str | None:
    """提取手机号中的数字，用于查重和检索。"""
    if not phone:
        return None
    import re
    return re.sub(r"\D", "", phone)


def _has_mask_pattern(value: str | None) -> bool:
    """检查值是否包含掩码特征（**** 或 ***）。"""
    if not value:
        return False
    return "****" in value or "***" in value


async def _get_customer_or_404(
    customer_id: UUID, db: AsyncSession, user_id: str, role_code: str
) -> Customer:
    """获取客户并校验数据范围，越权或不存在统一 404。"""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.is_deleted.is_(False))
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "客户不存在"}) from None
    # 写路径范围校验
    try:
        assert_object_scope(customer, user_id=user_id, role_code=role_code, action="view")
    except Exception:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "客户不存在"}) from None
    return customer


def _customer_to_list_dict(c: Customer, project_count: int = 0) -> dict:
    """列表序列化：不返回 PII，只返回 has_phone。"""
    return {
        "id": str(c.id),
        "customer_no": c.customer_no,
        "name": c.name,
        "source": c.source,
        "level": c.level,
        "stage": c.stage,
        "owner_sales_id": str(c.owner_sales_id),
        "has_phone": bool(c.phone),
        "budget_min": c.budget_min,
        "budget_max": c.budget_max,
        "project_count": project_count,
        "last_activity_at": c.last_activity_at.isoformat() if c.last_activity_at else None,
        "create_time": c.create_time.isoformat() if c.create_time else None,
    }


def _customer_to_detail_dict(c: Customer, owner_name: str | None = None) -> dict:
    """详情序列化：PII 掩码。"""
    return {
        "id": str(c.id),
        "customer_no": c.customer_no,
        "name": c.name,
        "source": c.source,
        "level": c.level,
        "stage": c.stage,
        "owner_sales_id": str(c.owner_sales_id),
        "owner_sales_name": owner_name,
        "phone_masked": mask_phone(c.phone),
        "wechat_masked": mask_wechat(c.wechat),
        "address_masked": mask_address(c.address),
        "has_phone": bool(c.phone),
        "budget_min": c.budget_min,
        "budget_max": c.budget_max,
        "style_preference": c.style_preference,
        "remark": c.remark,
        "last_activity_at": c.last_activity_at.isoformat() if c.last_activity_at else None,
        "create_time": c.create_time.isoformat() if c.create_time else None,
        "update_time": c.update_time.isoformat() if c.update_time else None,
    }


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("customer:view"))])
async def list_customers(
    request: Request,
    stage: str | None = Query(None),
    level: str | None = Query(None),
    owner_sales_id: UUID | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    sort: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    stmt = select(Customer).where(Customer.is_deleted.is_(False))

    # 数据范围
    stmt = apply_data_scope(stmt, user_id=user_id, role_code=role_code, model=Customer)

    # 筛选
    if stage is not None:
        if stage not in VALID_STAGES:
            raise HTTPException(status_code=422, detail={"code": 42201, "msg": "非法阶段值"})
        stmt = stmt.where(Customer.stage == stage)
    if level is not None:
        if level not in VALID_LEVELS:
            raise HTTPException(status_code=422, detail={"code": 42201, "msg": "非法等级值"})
        stmt = stmt.where(Customer.level == level)
    if owner_sales_id is not None:
        stmt = stmt.where(Customer.owner_sales_id == owner_sales_id)
    if q is not None:
        kw = f"%{q}%"
        # 仅持 customer:pii 者启用 phone_norm 搜索分支
        if "customer:pii" in request.state.permissions or role_code == "admin":
            phone_norm = _normalize_phone(q)
            if phone_norm:
                stmt = stmt.where(
                    or_(
                        Customer.name.ilike(kw),
                        Customer.phone_norm == phone_norm,
                        Customer.phone_norm.like(f"%{phone_norm[-4:]}"),
                    )
                )
            else:
                stmt = stmt.where(Customer.name.ilike(kw))
        else:
            stmt = stmt.where(Customer.name.ilike(kw))

    # 排序
    if sort == "-last_activity_at":
        stmt = stmt.order_by(Customer.last_activity_at.desc())
    elif sort == "last_activity_at":
        stmt = stmt.order_by(Customer.last_activity_at.asc())
    else:
        stmt = stmt.order_by(Customer.create_time.desc())

    # 计数
    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()

    # 分页
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    customers = result.scalars().all()

    # 批量获取 project_count
    customer_ids = [c.id for c in customers]
    project_counts = {}
    if customer_ids:
        pc_result = await db.execute(
            select(Project.customer_id, func.count())
            .where(Project.customer_id.in_(customer_ids), Project.is_deleted.is_(False))
            .group_by(Project.customer_id)
        )
        project_counts = {row[0]: row[1] for row in pc_result.all()}

    return {
        "code": 200,
        "data": {
            "list": [_customer_to_list_dict(c, project_counts.get(c.id, 0)) for c in customers],
            "total": total,
            "page": page,
            "size": size,
        },
    }


@router.post(
    "", response_model=dict, status_code=201,
    dependencies=[Depends(PermissionChecker("customer:edit"))],
)
async def create_customer(
    request: Request,
    customer_data: CustomerCreate,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id

    # 查重：phone_norm 精确匹配 + 后 4 位
    if customer_data.phone and not force:
        phone_norm = _normalize_phone(customer_data.phone)
        if phone_norm:
            existing = await db.execute(
                select(Customer).where(
                    Customer.phone_norm == phone_norm,
                    Customer.is_deleted.is_(False),
                )
            )
            candidates = existing.scalars().all()
            if candidates:
                return {
                    "code": 409,
                    "msg": "客户手机号疑似重复",
                    "data": {
                        "candidates": [
                            {"id": str(c.id), "name": c.name, "customer_no": c.customer_no}
                            for c in candidates
                        ]
                    },
                }

    # owner_sales_id 默认为当前用户
    owner_id = customer_data.owner_sales_id or UUID(user_id)

    customer = Customer(
        name=customer_data.name,
        source=customer_data.source,
        level=customer_data.level,
        stage="lead",
        owner_sales_id=owner_id,
        phone=customer_data.phone,
        phone_norm=_normalize_phone(customer_data.phone),
        wechat=customer_data.wechat,
        address=customer_data.address,
        budget_min=customer_data.budget_min,
        budget_max=customer_data.budget_max,
        style_preference=customer_data.style_preference,
        remark=customer_data.remark,
        created_by=UUID(user_id),
        updated_by=UUID(user_id),
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    return {"code": 200, "data": _customer_to_detail_dict(customer)}


@router.get(
    "/{customer_id}", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:view"))],
)
async def get_customer(
    request: Request,
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    customer = await _get_customer_or_404(customer_id, db, user_id, role_code)

    # 获取 owner 名称
    owner_name = None
    owner_result = await db.execute(
        select(User.username).where(User.id == customer.owner_sales_id)
    )
    owner_name = owner_result.scalar_one_or_none()

    return {"code": 200, "data": _customer_to_detail_dict(customer, owner_name)}


@router.put(
    "/{customer_id}", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:edit"))],
)
async def update_customer(
    request: Request,
    customer_id: UUID,
    customer_data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    customer = await _get_customer_or_404(customer_id, db, user_id, role_code)

    # 检查掩码特征
    update_fields = set(customer_data.model_fields_set)
    for field in update_fields:
        value = getattr(customer_data, field)
        if isinstance(value, str) and _has_mask_pattern(value):
            raise HTTPException(
                status_code=422,
                detail={"code": 40001, "msg": f"字段 {field} 包含掩码特征，不可提交"},
            )

    # 部分更新：只更新提供的字段
    for field in update_fields:
        setattr(customer, field, getattr(customer_data, field))

    # 如果更新了 phone，同步更新 phone_norm
    if "phone" in update_fields:
        customer.phone_norm = _normalize_phone(customer.phone)

    customer.updated_by = UUID(user_id)
    await db.commit()
    await db.refresh(customer)

    owner_name = None
    owner_result = await db.execute(
        select(User.username).where(User.id == customer.owner_sales_id)
    )
    owner_name = owner_result.scalar_one_or_none()

    return {"code": 200, "data": _customer_to_detail_dict(customer, owner_name)}


@router.patch(
    "/{customer_id}/stage", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:edit"))],
)
async def transition_stage(
    request: Request,
    customer_id: UUID,
    transition_data: StageTransitionRequest,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    customer = await _get_customer_or_404(customer_id, db, user_id, role_code)

    # 验证目标阶段
    if transition_data.to_stage not in VALID_STAGES:
        raise HTTPException(status_code=422, detail={"code": 42201, "msg": "非法目标阶段"})

    # 状态机验证
    result = validate_transition(customer.stage, transition_data.to_stage, transition_data.reason)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail={"code": result["code"], "msg": result["msg"]})

    old_stage = customer.stage
    customer.stage = transition_data.to_stage
    customer.updated_by = UUID(user_id)

    # 写阶段日志
    stage_log = EntityStageLog(
        entity_type="customer",
        entity_id=customer.id,
        from_stage=old_stage,
        to_stage=transition_data.to_stage,
        reason=transition_data.reason,
        operator_id=UUID(user_id),
        created_by=UUID(user_id),
        updated_by=UUID(user_id),
    )
    db.add(stage_log)

    await db.commit()
    await db.refresh(customer)

    return {"code": 200, "data": _customer_to_detail_dict(customer)}


@router.delete("/{customer_id}", dependencies=[Depends(PermissionChecker("customer:edit"))])
async def delete_customer(
    request: Request,
    customer_id: UUID,
    cascade: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    customer = await _get_customer_or_404(customer_id, db, user_id, role_code)

    # 检查未删除的子记录
    sub_counts = {}
    for model, name in [
        (CustomerDialogue, "dialogue"), (FollowUp, "follow_up"), (Requirement, "requirement")
    ]:
        count_result = await db.execute(
            select(func.count()).where(
                model.customer_id == customer_id, model.is_deleted.is_(False)
            )
        )
        sub_counts[name] = count_result.scalar_one()

    has_sub = any(v > 0 for v in sub_counts.values())

    if has_sub and not cascade:
        raise HTTPException(
            status_code=409,
            detail={"code": 40902, "msg": "存在未处理子记录，拒绝删除"},
        )

    if has_sub and cascade:
        # 仅 admin/manager 可级联删除
        if role_code not in ("admin", "manager"):
            raise HTTPException(
                status_code=403,
                detail={"code": 40301, "msg": "仅 admin/manager 可级联删除"},
            )
        # 级联软删子记录
        for model in [CustomerDialogue, FollowUp, Requirement]:
            await db.execute(
                model.__table__.update()
                .where(model.customer_id == customer_id, model.is_deleted.is_(False))
                .values(is_deleted=True, deleted_at=datetime.utcnow())
            )

    customer.is_deleted = True
    customer.deleted_at = datetime.utcnow()
    customer.updated_by = UUID(user_id)
    await db.commit()

    return {"code": 200, "msg": "success"}


@router.get(
    "/{customer_id}/pii", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:pii"))],
)
@audit_action("customer_pii_view", module="customers", target_id_kwarg="customer_id")
async def view_pii(
    request: Request,
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    customer = await _get_customer_or_404(customer_id, db, user_id, role_code)

    # TODO: Redis 限速 30 次/时/用户
    # key = f"pii_rate:{user_id}"
    # count = redis.incr(key)
    # if count == 1: redis.expire(key, 3600)
    # if count > 30: raise HTTPException(429, {"code": 42901, "msg": "PII 查看超速"})

    return {
        "code": 200,
        "data": {
            "phone": customer.phone,
            "wechat": customer.wechat,
            "address": customer.address,
        },
    }


@router.put(
    "/{customer_id}/owner", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:transfer"))],
)
@audit_action("customer_transfer", module="customers", target_id_kwarg="customer_id")
async def transfer_owner(
    request: Request,
    customer_id: UUID,
    new_owner_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    customer = await _get_customer_or_404(customer_id, db, user_id, role_code)

    customer.owner_sales_id = new_owner_id
    customer.updated_by = UUID(user_id)

    # 重指派 pending/sent 跟进提醒
    await db.execute(
        Reminder.__table__.update()
        .where(
            Reminder.target_type == "follow_up",
            Reminder.target_id.in_(
                select(FollowUp.id).where(
                    FollowUp.customer_id == customer_id, FollowUp.is_deleted.is_(False)
                )
            ),
            Reminder.status.in_(["pending", "sent"]),
            Reminder.is_deleted.is_(False),
        )
        .values(assignee_id=new_owner_id)
    )

    await db.commit()
    await db.refresh(customer)

    return {"code": 200, "data": _customer_to_detail_dict(customer)}


@router.get(
    "/{customer_id}/summary", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:view"))],
)
async def get_summary(
    request: Request,
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    customer = await _get_customer_or_404(customer_id, db, user_id, role_code)

    # project_count
    project_result = await db.execute(
        select(func.count()).where(
            Project.customer_id == customer_id, Project.is_deleted.is_(False)
        )
    )
    project_count = project_result.scalar_one()

    # proposal_count
    proposal_result = await db.execute(
        select(func.count()).where(
            Proposal.customer_name == customer.name, Proposal.is_deleted.is_(False)
        )
    )
    proposal_count = proposal_result.scalar_one()

    # confirmed_amount（仅 admin/manager/sales 可见）
    confirmed_amount = None
    amount_visible = role_code in _AMOUNT_VISIBLE_ROLES
    if amount_visible:
        amount_result = await db.execute(
            select(func.coalesce(func.sum(Quotation.total_amount), 0))
            .select_from(Quotation)
            .join(Proposal, Quotation.proposal_id == Proposal.id)
            .where(
                Proposal.customer_name == customer.name,
                Quotation.status == "confirmed",
                Quotation.is_deleted.is_(False),
                Proposal.is_deleted.is_(False),
            )
        )
        confirmed_amount = amount_result.scalar_one()

    return {
        "code": 200,
        "data": {
            "project_count": project_count,
            "proposal_count": proposal_count,
            "confirmed_amount": confirmed_amount,
            "confirmed_amount_visible": amount_visible,
        },
    }


@router.get(
    "/{customer_id}/timeline", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:view"))],
)
async def get_timeline(
    request: Request,
    customer_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    await _get_customer_or_404(customer_id, db, user_id, role_code)

    # 合并查询：dialogues + follow_ups + requirements + stage_logs
    items = []

    # Dialogues
    dlg_result = await db.execute(
        select(CustomerDialogue)
        .where(CustomerDialogue.customer_id == customer_id, CustomerDialogue.is_deleted.is_(False))
        .order_by(CustomerDialogue.occurred_at.desc())
    )
    for d in dlg_result.scalars().all():
        items.append({
            "type": "dialogue",
            "id": d.id,
            "content": d.content[:200],
            "created_at": d.occurred_at.isoformat() if d.occurred_at else d.create_time.isoformat(),
            "operator_name": None,
        })

    # Follow-ups
    fu_result = await db.execute(
        select(FollowUp)
        .where(FollowUp.customer_id == customer_id, FollowUp.is_deleted.is_(False))
        .order_by(FollowUp.create_time.desc())
    )
    for f in fu_result.scalars().all():
        items.append({
            "type": "follow_up",
            "id": f.id,
            "content": f.content[:200],
            "created_at": f.create_time.isoformat() if f.create_time else None,
            "operator_name": None,
        })

    # Requirements
    req_result = await db.execute(
        select(Requirement)
        .where(Requirement.customer_id == customer_id, Requirement.is_deleted.is_(False))
        .order_by(Requirement.create_time.desc())
    )
    for r in req_result.scalars().all():
        items.append({
            "type": "requirement",
            "id": r.id,
            "content": r.content[:200],
            "created_at": r.create_time.isoformat() if r.create_time else None,
            "operator_name": None,
        })

    # Stage logs
    log_result = await db.execute(
        select(EntityStageLog)
        .where(
            EntityStageLog.entity_type == "customer",
            EntityStageLog.entity_id == customer_id,
            EntityStageLog.is_deleted.is_(False),
        )
        .order_by(EntityStageLog.create_time.desc())
    )
    for log in log_result.scalars().all():
        items.append({
            "type": "stage_change",
            "id": log.id,
            "content": f"{log.from_stage} -> {log.to_stage}",
            "created_at": log.create_time.isoformat() if log.create_time else None,
            "operator_name": None,
        })

    # 按时间排序
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)

    total = len(items)
    start = (page - 1) * size
    end = start + size
    paged_items = items[start:end]

    return {
        "code": 200,
        "data": {
            "list": paged_items,
            "total": total,
            "page": page,
            "size": size,
        },
    }


# ---------------------------------------------------------------------------
# 子资源：Dialogues
# ---------------------------------------------------------------------------

@router.get(
    "/{customer_id}/dialogues", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:view"))],
)
async def list_dialogues(
    request: Request,
    customer_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    await _get_customer_or_404(customer_id, db, user_id, role_code)

    stmt = (
        select(CustomerDialogue)
        .where(CustomerDialogue.customer_id == customer_id, CustomerDialogue.is_deleted.is_(False))
        .order_by(CustomerDialogue.occurred_at.desc())
    )
    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "code": 200,
        "data": {
            "list": [
                {
                    "id": str(d.id),
                    "channel": d.channel,
                    "direction": d.direction,
                    "content": d.content,
                    "occurred_at": d.occurred_at.isoformat() if d.occurred_at else None,
                    "create_time": d.create_time.isoformat() if d.create_time else None,
                }
                for d in items
            ],
            "total": total,
            "page": page,
            "size": size,
        },
    }


@router.post(
    "/{customer_id}/dialogues", response_model=dict, status_code=201,
    dependencies=[Depends(PermissionChecker("customer:edit"))],
)
async def create_dialogue(
    request: Request,
    customer_id: UUID,
    channel: str = Query("wechat"),
    direction: str = Query("in"),
    content: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    await _get_customer_or_404(customer_id, db, user_id, role_code)

    dialogue = CustomerDialogue(
        customer_id=customer_id,
        channel=channel,
        direction=direction,
        content=content,
        created_by=UUID(user_id),
        updated_by=UUID(user_id),
    )
    db.add(dialogue)
    await db.commit()
    await db.refresh(dialogue)

    return {
        "code": 200,
        "data": {
            "id": str(dialogue.id),
            "channel": dialogue.channel,
            "direction": dialogue.direction,
            "content": dialogue.content,
            "occurred_at": dialogue.occurred_at.isoformat() if dialogue.occurred_at else None,
        },
    }


# ---------------------------------------------------------------------------
# 子资源：Requirements
# ---------------------------------------------------------------------------

@router.get(
    "/{customer_id}/requirements", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:view"))],
)
async def list_requirements(
    request: Request,
    customer_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    await _get_customer_or_404(customer_id, db, user_id, role_code)

    stmt = (
        select(Requirement)
        .where(Requirement.customer_id == customer_id, Requirement.is_deleted.is_(False))
        .order_by(Requirement.create_time.desc())
    )
    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "code": 200,
        "data": {
            "list": [
                {
                    "id": str(r.id),
                    "content": r.content,
                    "source": r.source,
                    "confirmed": r.confirmed,
                    "create_time": r.create_time.isoformat() if r.create_time else None,
                }
                for r in items
            ],
            "total": total,
            "page": page,
            "size": size,
        },
    }


@router.post(
    "/{customer_id}/requirements", response_model=dict, status_code=201,
    dependencies=[Depends(PermissionChecker("customer:edit"))],
)
async def create_requirement(
    request: Request,
    customer_id: UUID,
    content: str = Query(...),
    source: str = Query("manual"),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    await _get_customer_or_404(customer_id, db, user_id, role_code)

    req = Requirement(
        customer_id=customer_id,
        content=content,
        source=source,
        created_by=UUID(user_id),
        updated_by=UUID(user_id),
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    return {
        "code": 200,
        "data": {
            "id": str(req.id),
            "content": req.content,
            "source": req.source,
            "confirmed": req.confirmed,
        },
    }


# ---------------------------------------------------------------------------
# 子资源：Follow-ups
# ---------------------------------------------------------------------------

@router.get(
    "/{customer_id}/follow-ups", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:view"))],
)
async def list_follow_ups(
    request: Request,
    customer_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    await _get_customer_or_404(customer_id, db, user_id, role_code)

    stmt = (
        select(FollowUp)
        .where(FollowUp.customer_id == customer_id, FollowUp.is_deleted.is_(False))
        .order_by(FollowUp.create_time.desc())
    )
    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "code": 200,
        "data": {
            "list": [
                {
                    "id": str(f.id),
                    "method": f.method,
                    "content": f.content,
                    "result": f.result,
                    "next_follow_at": f.next_follow_at.isoformat() if f.next_follow_at else None,
                    "done_at": f.done_at.isoformat() if f.done_at else None,
                    "create_time": f.create_time.isoformat() if f.create_time else None,
                }
                for f in items
            ],
            "total": total,
            "page": page,
            "size": size,
        },
    }


@router.post(
    "/{customer_id}/follow-ups", response_model=dict, status_code=201,
    dependencies=[Depends(PermissionChecker("customer:edit"))],
)
async def create_follow_up(
    request: Request,
    customer_id: UUID,
    method: str = Query("wechat"),
    content: str = Query(...),
    result: str | None = Query(None),
    next_follow_at: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    await _get_customer_or_404(customer_id, db, user_id, role_code)

    follow_up = FollowUp(
        customer_id=customer_id,
        follower_id=UUID(user_id),
        method=method,
        content=content,
        result=result,
        next_follow_at=next_follow_at,
        created_by=UUID(user_id),
        updated_by=UUID(user_id),
    )
    db.add(follow_up)
    await db.commit()
    await db.refresh(follow_up)

    return {
        "code": 200,
        "data": {
            "id": str(follow_up.id),
            "method": follow_up.method,
            "content": follow_up.content,
            "result": follow_up.result,
            "next_follow_at": (
                follow_up.next_follow_at.isoformat() if follow_up.next_follow_at else None
            ),
        },
    }


# ---------------------------------------------------------------------------
# 子资源：Proposals
# ---------------------------------------------------------------------------

@router.get(
    "/{customer_id}/proposals", response_model=dict,
    dependencies=[Depends(PermissionChecker("customer:view"))],
)
async def list_proposals(
    request: Request,
    customer_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    customer = await _get_customer_or_404(customer_id, db, user_id, role_code)

    stmt = (
        select(Proposal)
        .where(Proposal.customer_name == customer.name, Proposal.is_deleted.is_(False))
        .order_by(Proposal.create_time.desc())
    )
    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "code": 200,
        "data": {
            "list": [
                {
                    "id": str(p.id),
                    "proposal_no": p.proposal_no,
                    "proposal_name": p.proposal_name,
                    "status": p.status,
                    "total_face_value": p.total_face_value,
                    "create_time": p.create_time.isoformat() if p.create_time else None,
                }
                for p in items
            ],
            "total": total,
            "page": page,
            "size": size,
        },
    }


@router.post(
    "/{customer_id}/proposals", response_model=dict, status_code=201,
    dependencies=[Depends(PermissionChecker("customer:edit"))],
)
async def create_proposal(
    request: Request,
    customer_id: UUID,
    proposal_name: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code
    customer = await _get_customer_or_404(customer_id, db, user_id, role_code)

    proposal = Proposal(
        proposal_no=f"PR-{datetime.now().strftime('%Y%m%d')}-{str(uuid4())[:8].upper()}",
        proposal_name=proposal_name,
        creator_id=UUID(user_id),
        customer_name=customer.name,
        status="draft",
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)

    return {
        "code": 200,
        "data": {
            "id": str(proposal.id),
            "proposal_no": proposal.proposal_no,
            "proposal_name": proposal.proposal_name,
            "status": proposal.status,
            "customer_name": proposal.customer_name,
        },
    }
