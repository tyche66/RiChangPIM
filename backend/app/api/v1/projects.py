"""项目域 API（HLD §8.3）。

挂 PermissionChecker + apply_data_scope + assert_object_scope。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.data_scope import (
    NotFoundError,
    apply_data_scope,
    assert_object_scope,
)
from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.customer import Customer
from app.models.project import Project, ProjectAsset, ProjectMember
from app.models.sales import Proposal
from app.models.user import User
from app.schemas.project import (
    CustomerBrief,
    ProjectAssetCreate,
    ProjectAssetStatusUpdate,
    ProjectCreate,
    ProjectMemberCreate,
    ProjectStageUpdate,
    ProjectUpdate,
)
from app.services.project_state import STAGES, auto_update_status, validate_transition

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

_VALID_STAGES = set(STAGES) | {"cancelled"}
_VALID_STATUSES = {"active", "paused", "done", "cancelled"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_project_or_404(
    db: AsyncSession, project_id: UUID, *, load_customer: bool = False
) -> Project:
    """获取项目，不存在返回 404。"""
    stmt = select(Project).where(
        Project.id == project_id, Project.is_deleted.is_(False)
    )
    if load_customer:
        stmt = stmt.options(selectinload(Project.customer))
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        )
    return project


def _project_to_dict(
    project: Project, *, customer_brief: CustomerBrief | None = None
) -> dict:
    """序列化项目为 dict。"""
    return {
        "id": str(project.id),
        "customer_id": str(project.customer_id),
        "customer_brief": customer_brief.model_dump() if customer_brief else None,
        "code": project.code,
        "name": project.name,
        "project_type": project.project_type,
        "stage": project.stage,
        "status": project.status,
        "budget": project.budget,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "remark": project.remark,
        "last_activity_at": project.last_activity_at.isoformat()
        if project.last_activity_at
        else None,
        "create_time": project.create_time.isoformat() if project.create_time else None,
        "update_time": project.update_time.isoformat() if project.update_time else None,
    }


def _is_designer(user_id, role_code) -> bool:
    return role_code == "designer"


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("project:view"))])
async def list_projects(
    request: Request,
    stage: str | None = Query(None),
    status: str | None = Query(None),
    customer_id: UUID | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    stmt = select(Project).where(Project.is_deleted.is_(False))

    # Data scope
    stmt = apply_data_scope(stmt, user_id=user_id, role_code=role_code, model=Project)

    # Filters
    if stage:
        if stage not in _VALID_STAGES:
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": f"无效的阶段: {stage}"}
            )
        stmt = stmt.where(Project.stage == stage)
    if status:
        if status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": f"无效的状态: {status}"}
            )
        stmt = stmt.where(Project.status == status)
    if customer_id:
        stmt = stmt.where(Project.customer_id == customer_id)
    if q:
        stmt = stmt.where(Project.name.ilike(f"%{q}%"))

    # Pagination
    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar() or 0

    stmt = stmt.order_by(Project.create_time.desc())
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    projects = result.scalars().all()

    # Build customer_brief for designer
    items = []
    for p in projects:
        brief = None
        if _is_designer(user_id, role_code):
            customer_result = await db.execute(
                select(Customer).where(Customer.id == p.customer_id)
            )
            customer = customer_result.scalar_one_or_none()
            if customer:
                brief = CustomerBrief(customer_no=customer.customer_no, name=customer.name)
        items.append(_project_to_dict(p, customer_brief=brief))

    return {
        "code": 200,
        "data": {"list": items, "total": total, "page": page, "size": size},
    }


@router.post(
    "", response_model=dict, status_code=201,
    dependencies=[Depends(PermissionChecker("project:edit"))],
)
@audit_action("project_create", module="projects")
async def create_project(
    request: Request,
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    # Verify customer access
    customer_result = await db.execute(
        select(Customer).where(
            Customer.id == data.customer_id, Customer.is_deleted.is_(False)
        )
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "客户不存在"}
        )

    # Check write scope for customer
    if role_code not in ("admin", "manager"):
        if customer.owner_sales_id != user_id:
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": "客户不存在"}
            )

    project = Project(
        customer_id=data.customer_id,
        name=data.name,
        code=data.code,
        project_type=data.project_type,
        stage="lead",
        status="active",
        budget=data.budget,
        start_date=data.start_date,
        end_date=data.end_date,
        remark=data.remark,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return {"code": 200, "data": _project_to_dict(project)}


@router.get(
    "/{project_id}", response_model=dict,
    dependencies=[Depends(PermissionChecker("project:view"))],
)
async def get_project(
    request: Request,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    project = await _get_project_or_404(db, project_id, load_customer=True)

    # Check read access
    if role_code not in ("admin", "manager"):
        if role_code == "sales":
            customer_result = await db.execute(
                select(Customer).where(Customer.id == project.customer_id)
            )
            customer = customer_result.scalar_one_or_none()
            if not customer or customer.owner_sales_id != user_id:
                # Check if member
                member_result = await db.execute(
                    select(ProjectMember).where(
                        ProjectMember.project_id == project_id,
                        ProjectMember.user_id == user_id,
                        ProjectMember.is_deleted.is_(False),
                    )
                )
                if not member_result.scalar_one_or_none():
                    raise HTTPException(
                        status_code=404, detail={"code": 40401, "msg": "项目不存在"}
                    )
        elif role_code == "designer":
            member_result = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == user_id,
                    ProjectMember.is_deleted.is_(False),
                )
            )
            if not member_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=404, detail={"code": 40401, "msg": "项目不存在"}
                )
        else:
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": "项目不存在"}
            )

    # Build response
    customer_brief = None
    if _is_designer(user_id, role_code) and project.customer:
        customer_brief = CustomerBrief(
            customer_no=project.customer.customer_no, name=project.customer.name
        )

    return {"code": 200, "data": _project_to_dict(project, customer_brief=customer_brief)}


@router.put(
    "/{project_id}", response_model=dict,
    dependencies=[Depends(PermissionChecker("project:edit"))],
)
@audit_action("project_update", module="projects", target_id_kwarg="project_id")
async def update_project(
    request: Request,
    project_id: UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    project = await _get_project_or_404(db, project_id)

    # Check write scope
    try:
        assert_object_scope(
            project, user_id=user_id, role_code=role_code, action="project_update"
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        ) from None

    # Update fields (缺省=不改)
    update_fields = data.model_fields_set
    for field in update_fields:
        setattr(project, field, getattr(data, field))

    project.updated_by = user_id
    project.last_activity_at = func.now()

    await db.commit()
    await db.refresh(project)

    return {"code": 200, "data": _project_to_dict(project)}


@router.delete(
    "/{project_id}", response_model=dict,
    dependencies=[Depends(PermissionChecker("project:edit"))],
)
@audit_action("project_delete", module="projects", target_id_kwarg="project_id")
async def delete_project(
    request: Request,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    project = await _get_project_or_404(db, project_id)

    # Check write scope
    try:
        assert_object_scope(
            project, user_id=user_id, role_code=role_code, action="project_delete"
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        ) from None

    # Soft delete
    project.is_deleted = True
    project.updated_by = user_id

    # Cascade soft delete members and assets
    await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.is_deleted.is_(False)
        )
    )
    members_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.is_deleted.is_(False)
        )
    )
    for m in members_result.scalars().all():
        m.is_deleted = True

    assets_result = await db.execute(
        select(ProjectAsset).where(
            ProjectAsset.project_id == project_id, ProjectAsset.is_deleted.is_(False)
        )
    )
    for a in assets_result.scalars().all():
        a.is_deleted = True

    await db.commit()
    return {"code": 200, "msg": "success"}


# ---------------------------------------------------------------------------
# Stage transition
# ---------------------------------------------------------------------------


@router.patch(
    "/{project_id}/stage",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:edit"))],
)
@audit_action("project_stage_change", module="projects", target_id_kwarg="project_id")
async def update_project_stage(
    request: Request,
    project_id: UUID,
    data: ProjectStageUpdate,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    project = await _get_project_or_404(db, project_id)

    # Check write scope
    try:
        assert_object_scope(
            project, user_id=user_id, role_code=role_code, action="project_stage_change"
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        ) from None

    # Validate transition
    error = validate_transition(project.stage, data.to_stage, data.reason)
    if error:
        raise HTTPException(status_code=400, detail=error)

    project.stage = data.to_stage
    project.status = auto_update_status(data.to_stage)
    project.updated_by = user_id
    project.last_activity_at = func.now()

    await db.commit()
    await db.refresh(project)

    return {"code": 200, "data": _project_to_dict(project)}


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/members",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:member"))],
)
async def list_members(
    request: Request,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    project = await _get_project_or_404(db, project_id)

    # Check write scope
    try:
        assert_object_scope(
            project, user_id=user_id, role_code=role_code, action="list_members"
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        ) from None

    result = await db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.is_deleted.is_(False),
        )
        .order_by(ProjectMember.create_time)
    )
    rows = result.all()

    items = []
    for m, u in rows:
        items.append(
            {
                "id": str(m.id),
                "project_id": str(m.project_id),
                "user_id": str(m.user_id),
                "member_role": m.member_role,
                "is_primary": m.is_primary,
                "username": u.username,
                "create_time": m.create_time.isoformat() if m.create_time else None,
            }
        )

    return {"code": 200, "data": {"list": items, "total": len(items)}}


@router.post(
    "/{project_id}/members",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("project:member"))],
)
@audit_action("project_member_add", module="projects", target_id_kwarg="project_id")
async def add_member(
    request: Request,
    project_id: UUID,
    data: ProjectMemberCreate,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    project = await _get_project_or_404(db, project_id)

    # Check write scope
    try:
        assert_object_scope(
            project, user_id=user_id, role_code=role_code, action="add_member"
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        ) from None

    # Check if user exists
    user_result = await db.execute(
        select(User).where(User.id == data.user_id, User.is_deleted.is_(False))
    )
    if not user_result.scalar_one_or_none():
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "用户不存在"}
        )

    # Check for duplicate
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == data.user_id,
            ProjectMember.member_role == data.member_role,
            ProjectMember.is_deleted.is_(False),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={"code": 40903, "msg": "该用户已绑定此角色"},
        )

    member = ProjectMember(
        project_id=project_id,
        user_id=data.user_id,
        member_role=data.member_role,
        is_primary=data.is_primary,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)

    return {
        "code": 200,
        "data": {
            "id": str(member.id),
            "project_id": str(member.project_id),
            "user_id": str(member.user_id),
            "member_role": member.member_role,
            "is_primary": member.is_primary,
        },
    }


@router.delete(
    "/{project_id}/members/{user_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:member"))],
)
@audit_action("project_member_remove", module="projects", target_id_kwarg="project_id")
async def remove_member(
    request: Request,
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    role_code = request.state.role_code
    current_user_id = request.state.user_id

    project = await _get_project_or_404(db, project_id)

    # Check write scope
    try:
        assert_object_scope(
            project, user_id=current_user_id, role_code=role_code, action="remove_member"
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        ) from None

    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.is_deleted.is_(False),
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "成员不存在"}
        )

    member.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/assets",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:asset"))],
)
async def list_assets(
    request: Request,
    project_id: UUID,
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    await _get_project_or_404(db, project_id)

    # Check access
    if role_code == "designer":
        member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_deleted.is_(False),
            )
        )
        if not member_result.scalar_one_or_none():
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": "项目不存在"}
            )
    elif role_code not in ("admin", "manager", "sales"):
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        )

    stmt = select(ProjectAsset).where(
        ProjectAsset.project_id == project_id,
        ProjectAsset.is_deleted.is_(False),
    )
    if category:
        stmt = stmt.where(ProjectAsset.category == category)

    stmt = stmt.order_by(ProjectAsset.create_time.desc())
    result = await db.execute(stmt)
    assets = result.scalars().all()

    items = []
    for a in assets:
        items.append(
            {
                "id": str(a.id),
                "project_id": str(a.project_id),
                "category": a.category,
                "name": a.name,
                "version": a.version,
                "is_current": a.is_current,
                "status": a.status,
                "attachment_id": str(a.attachment_id),
                "remark": a.remark,
                "create_time": a.create_time.isoformat() if a.create_time else None,
                "update_time": a.update_time.isoformat() if a.update_time else None,
            }
        )

    return {"code": 200, "data": {"list": items, "total": len(items)}}


@router.post(
    "/{project_id}/assets",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(PermissionChecker("project:asset"))],
)
@audit_action("project_asset_add", module="projects", target_id_kwarg="project_id")
async def add_asset(
    request: Request,
    project_id: UUID,
    data: ProjectAssetCreate,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    await _get_project_or_404(db, project_id)

    # Check access
    if role_code == "designer":
        member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_deleted.is_(False),
            )
        )
        if not member_result.scalar_one_or_none():
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": "项目不存在"}
            )
    elif role_code not in ("admin", "manager", "sales"):
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        )

    # Check for existing asset with same (project, category, name)
    existing_result = await db.execute(
        select(ProjectAsset).where(
            ProjectAsset.project_id == project_id,
            ProjectAsset.category == data.category,
            ProjectAsset.name == data.name,
            ProjectAsset.is_deleted.is_(False),
        )
    )
    existing = existing_result.scalars().all()

    if existing:
        # Version +1, old is_current=false
        max_version = max(a.version for a in existing)
        new_version = max_version + 1
        for a in existing:
            a.is_current = False
    else:
        new_version = 1

    asset = ProjectAsset(
        project_id=project_id,
        category=data.category,
        name=data.name,
        version=new_version,
        is_current=True,
        status="draft",
        attachment_id=data.attachment_id,
        remark=data.remark,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    return {
        "code": 200,
        "data": {
            "id": str(asset.id),
            "project_id": str(asset.project_id),
            "category": asset.category,
            "name": asset.name,
            "version": asset.version,
            "is_current": asset.is_current,
            "status": asset.status,
            "attachment_id": str(asset.attachment_id),
            "remark": asset.remark,
        },
    }


@router.patch(
    "/{project_id}/assets/{asset_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:asset"))],
)
@audit_action("project_asset_status", module="projects", target_id_kwarg="asset_id")
async def update_asset_status(
    request: Request,
    project_id: UUID,
    asset_id: UUID,
    data: ProjectAssetStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    await _get_project_or_404(db, project_id)

    # Check access
    if role_code == "designer":
        member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_deleted.is_(False),
            )
        )
        if not member_result.scalar_one_or_none():
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": "项目不存在"}
            )
    elif role_code not in ("admin", "manager", "sales"):
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "项目不存在"}
        )

    result = await db.execute(
        select(ProjectAsset).where(
            ProjectAsset.id == asset_id,
            ProjectAsset.project_id == project_id,
            ProjectAsset.is_deleted.is_(False),
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "资产不存在"}
        )

    asset.status = data.status
    asset.updated_by = user_id

    await db.commit()
    await db.refresh(asset)

    return {
        "code": 200,
        "data": {
            "id": str(asset.id),
            "project_id": str(asset.project_id),
            "category": asset.category,
            "name": asset.name,
            "version": asset.version,
            "is_current": asset.is_current,
            "status": asset.status,
            "attachment_id": str(asset.attachment_id),
            "remark": asset.remark,
        },
    }


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/proposals",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:view"))],
)
async def list_proposals(
    request: Request,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id
    role_code = request.state.role_code

    project = await _get_project_or_404(db, project_id)

    # Check read access
    if role_code not in ("admin", "manager"):
        if role_code == "sales":
            customer_result = await db.execute(
                select(Customer).where(Customer.id == project.customer_id)
            )
            customer = customer_result.scalar_one_or_none()
            if not customer or customer.owner_sales_id != user_id:
                member_result = await db.execute(
                    select(ProjectMember).where(
                        ProjectMember.project_id == project_id,
                        ProjectMember.user_id == user_id,
                        ProjectMember.is_deleted.is_(False),
                    )
                )
                if not member_result.scalar_one_or_none():
                    raise HTTPException(
                        status_code=404, detail={"code": 40401, "msg": "项目不存在"}
                    )
        elif role_code == "designer":
            member_result = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == user_id,
                    ProjectMember.is_deleted.is_(False),
                )
            )
            if not member_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=404, detail={"code": 40401, "msg": "项目不存在"}
                )
        else:
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": "项目不存在"}
            )

    stmt = select(Proposal).where(
        Proposal.project_id == project_id,
        Proposal.is_deleted.is_(False),
    ).order_by(Proposal.create_time.desc())

    result = await db.execute(stmt)
    proposals = result.scalars().all()

    items = []
    for p in proposals:
        items.append(
            {
                "id": str(p.id),
                "proposal_no": p.proposal_no,
                "proposal_name": p.proposal_name,
                "customer_name": p.customer_name,
                "status": p.status,
                "total_face_value": p.total_face_value,
                "create_time": p.create_time.isoformat() if p.create_time else None,
            }
        )

    return {"code": 200, "data": {"list": items, "total": len(items)}}
