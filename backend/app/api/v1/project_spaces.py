"""项目空间（楼层/房间/区域）API（Track C）。

空间必须属于某个项目；没有选择项目时不可选择项目空间。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.project import Project
from app.models.sales import ProjectSpace

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

_VALID_TYPES = {"floor", "room", "zone", "other"}


def _envelope(data, code: int = 200) -> dict:
    return {"code": code, "data": data}


def _now() -> datetime:
    return datetime.now(UTC)


def _space_to_dict(space: ProjectSpace) -> dict:
    return {
        "id": str(space.id),
        "project_id": str(space.project_id),
        "parent_id": str(space.parent_id) if space.parent_id else None,
        "space_type": space.space_type,
        "space_name": space.space_name,
        "level": space.level,
        "sort": space.sort,
        "create_time": space.create_time.isoformat() if space.create_time else None,
    }


async def _get_project_or_404(project_id: UUID, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted.is_(False))
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "项目不存在"})
    return project


class SpaceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    space_name: str = Field(min_length=1, max_length=128)
    space_type: str = Field(default="other", pattern="^(floor|room|zone|other)$")
    parent_id: UUID | None = None
    sort: int = 0


class SpaceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    space_name: str | None = Field(default=None, min_length=1, max_length=128)
    space_type: str | None = Field(default=None, pattern="^(floor|room|zone|other)$")
    parent_id: UUID | None = None
    sort: int | None = None


@router.get(
    "/{project_id}/spaces",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:view"))],
)
async def list_spaces(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """按项目列出空间树（扁平列表 + parent_id，前端组装树）。"""
    await _get_project_or_404(project_id, db)
    result = await db.execute(
        select(ProjectSpace)
        .where(
            ProjectSpace.project_id == project_id,
            ProjectSpace.is_deleted.is_(False),
        )
        .order_by(ProjectSpace.level, ProjectSpace.sort, ProjectSpace.space_name)
    )
    return _envelope([_space_to_dict(s) for s in result.scalars().all()])


@router.post(
    "/{project_id}/spaces",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:edit"))],
)
@audit_action("project_space_create", module="project")
async def create_space(
    request: Request,
    project_id: UUID,
    payload: SpaceCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """在指定项目下创建空间节点。"""
    await _get_project_or_404(project_id, db)

    parent_id = payload.parent_id
    if parent_id is not None:
        parent = (
            (
                await db.execute(
                    select(ProjectSpace).where(
                        ProjectSpace.id == parent_id,
                        ProjectSpace.project_id == project_id,
                        ProjectSpace.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .first()
        )
        if parent is None:
            raise HTTPException(
                status_code=400,
                detail={"code": 40010, "msg": "父空间不存在或不属于该项目"},
            )
        level = parent.level + 1
    else:
        level = 1

    space = ProjectSpace(
        id=uuid4(),
        project_id=project_id,
        parent_id=parent_id,
        space_type=payload.space_type,
        space_name=payload.space_name,
        level=level,
        sort=payload.sort,
        create_time=_now(),
        update_time=_now(),
    )
    db.add(space)
    await db.commit()
    await db.refresh(space)
    return _envelope(_space_to_dict(space))


@router.put(
    "/{project_id}/spaces/{space_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:edit"))],
)
@audit_action("project_space_update", module="project")
async def update_space(
    request: Request,
    project_id: UUID,
    space_id: UUID,
    payload: SpaceUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    await _get_project_or_404(project_id, db)
    result = await db.execute(
        select(ProjectSpace).where(
            ProjectSpace.id == space_id,
            ProjectSpace.project_id == project_id,
            ProjectSpace.is_deleted.is_(False),
        )
    )
    space = result.scalar_one_or_none()
    if space is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "空间不存在"})

    parent_id = payload.parent_id if payload.parent_id is not None else space.parent_id
    if parent_id is not None:
        if parent_id == space_id:
            raise HTTPException(
                status_code=400, detail={"code": 40010, "msg": "父空间不能是自己"}
            )
        parent = (
            (
                await db.execute(
                    select(ProjectSpace).where(
                        ProjectSpace.id == parent_id,
                        ProjectSpace.project_id == project_id,
                        ProjectSpace.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .first()
        )
        if parent is None:
            raise HTTPException(
                status_code=400,
                detail={"code": 40010, "msg": "父空间不存在或不属于该项目"},
            )
        space.level = parent.level + 1

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "parent_id":
            continue
        setattr(space, key, value)
    space.parent_id = parent_id
    space.update_time = _now()
    await db.commit()
    await db.refresh(space)
    return _envelope(_space_to_dict(space))


@router.delete(
    "/{project_id}/spaces/{space_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("project:edit"))],
)
@audit_action("project_space_delete", module="project")
async def delete_space(
    request: Request,
    project_id: UUID,
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """软删除空间节点（子空间一并软删，明细的 project_space_id 置空）。"""
    await _get_project_or_404(project_id, db)
    result = await db.execute(
        select(ProjectSpace).where(
            ProjectSpace.id == space_id,
            ProjectSpace.project_id == project_id,
            ProjectSpace.is_deleted.is_(False),
        )
    )
    space = result.scalar_one_or_none()
    if space is None:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "空间不存在"})

    # 收集自身与所有子孙
    to_delete: list[ProjectSpace] = [space]
    changed = True
    while changed:
        changed = False
        current_ids = {s.id for s in to_delete}
        children = (
            (
                await db.execute(
                    select(ProjectSpace).where(
                        ProjectSpace.project_id == project_id,
                        ProjectSpace.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        for child in children:
            if child.parent_id in current_ids and child.id not in current_ids:
                to_delete.append(child)
                changed = True

    for node in to_delete:
        node.is_deleted = True
        node.deleted_at = _now()
        node.update_time = _now()
    await db.commit()
    return _envelope({"id": str(space_id), "deleted": len(to_delete)})
