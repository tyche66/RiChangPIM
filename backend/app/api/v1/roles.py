from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.user import Permission, Role, RolePermission, User
from app.schemas.user import RoleCreate, RoleResponse

router = APIRouter()


async def _role_response(role: Role, db: AsyncSession) -> RoleResponse:
    result = await db.execute(
        select(Permission.perm_code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(
            RolePermission.role_id == role.id,
            RolePermission.is_deleted.is_(False),
            Permission.is_deleted.is_(False),
        )
    )
    response = RoleResponse.model_validate(role)
    response.permission_ids = [row.perm_code for row in result.fetchall()]
    return response


async def _resolve_permission_codes(
    db: AsyncSession, permission_ids: list[str] | None
) -> set[str]:
    if not permission_ids:
        return set()
    result = await db.execute(select(Permission).where(Permission.is_deleted.is_(False)))
    permissions = result.scalars().all()
    by_code = {p.perm_code for p in permissions}
    by_id = {str(p.id): p.perm_code for p in permissions}
    return {by_id.get(item, item) for item in permission_ids}


def _require_admin(request: Request, message: str) -> None:
    if getattr(request.state, "role_code", None) != "admin":
        raise HTTPException(status_code=403, detail={"code": 40301, "msg": message})


async def _actor_role_id(request: Request, db: AsyncSession):
    raw = getattr(request.state, "user_id", None)
    if not raw:
        return None
    try:
        user_id = UUID(str(raw))
    except (TypeError, ValueError):
        return None
    user = await db.get(User, user_id)
    return user.role_id if user else None


async def _bump_role_tokens(role_id, db: AsyncSession) -> None:
    await db.execute(
        update(User)
        .where(User.role_id == role_id)
        .values(token_version=func.coalesce(User.token_version, 0) + 1)
    )


async def _sync_role_permissions(
    role: Role, permission_ids: list[str] | None, db: AsyncSession
) -> None:
    if permission_ids is None:
        return

    requested = set(permission_ids)
    permission_result = await db.execute(select(Permission).where(Permission.is_deleted.is_(False)))
    permissions = permission_result.scalars().all()
    by_code = {p.perm_code: p for p in permissions}
    by_id = {str(p.id): p for p in permissions}

    selected: list[Permission] = []
    for item in requested:
        permission = by_code.get(item) or by_id.get(item)
        if not permission:
            raise HTTPException(
                status_code=400,
                detail={"code": 40001, "msg": f"权限不存在: {item}"},
            )
        selected.append(permission)

    existing_result = await db.execute(
        select(RolePermission).where(RolePermission.role_id == role.id)
    )
    existing = existing_result.scalars().all()
    existing_by_perm_id = {rp.permission_id: rp for rp in existing}
    selected_ids = {p.id for p in selected}

    for rp in existing:
        rp.is_deleted = rp.permission_id not in selected_ids

    for permission in selected:
        rp = existing_by_perm_id.get(permission.id)
        if rp:
            rp.is_deleted = False
        else:
            db.add(RolePermission(role_id=role.id, permission_id=permission.id))


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("role:view"))])
async def list_roles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role).where(Role.is_deleted.is_(False)))
    roles = result.scalars().all()
    return {"code": 200, "data": {"list": [await _role_response(r, db) for r in roles]}}


@router.post(
    "",
    response_model=RoleResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker("role:create"))],
)
@audit_action("role_create", module="roles", target_id_kwarg="id")
async def create_role(
    request: Request,
    role_data: RoleCreate,
    db: AsyncSession = Depends(get_db),
):
    if getattr(request.state, "role_code", None) != "admin":
        if role_data.role_code == "admin":
            raise HTTPException(
                status_code=403,
                detail={"code": 40301, "msg": "仅系统管理员可创建管理员角色"},
            )
        requested = await _resolve_permission_codes(db, role_data.permission_ids)
        granted = set(getattr(request.state, "permissions", []) or [])
        if requested - granted:
            raise HTTPException(
                status_code=403,
                detail={"code": 40301, "msg": "不能在角色中授予自己不具备的权限"},
            )

    result = await db.execute(
        select(Role).where(Role.role_code == role_data.role_code, Role.is_deleted.is_(False))
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail={"code": 40901, "msg": "角色编码已存在"})

    role = Role(
        role_name=role_data.role_name,
        role_code=role_data.role_code,
        description=role_data.description,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    await _sync_role_permissions(role, role_data.permission_ids, db)
    await db.commit()
    await db.refresh(role)
    return await _role_response(role, db)


@router.put(
    "/{role_id}",
    response_model=RoleResponse,
    dependencies=[Depends(PermissionChecker("role:edit"))],
)
@audit_action("role_perm_change", module="roles", target_id_kwarg="role_id")
async def update_role(
    request: Request,
    role_id: str,
    role_data: RoleCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Role).where(Role.id == UUID(role_id), Role.is_deleted.is_(False))
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "角色不存在"})

    actor_is_admin = getattr(request.state, "role_code", None) == "admin"
    if not actor_is_admin:
        if role.role_code == "admin":
            raise HTTPException(
                status_code=403,
                detail={"code": 40301, "msg": "仅系统管理员可修改管理员角色"},
            )
        actor_role_id = await _actor_role_id(request, db)
        if actor_role_id == role.id:
            raise HTTPException(
                status_code=403,
                detail={"code": 40301, "msg": "不能修改自己所属角色的权限"},
            )
        requested = await _resolve_permission_codes(db, role_data.permission_ids)
        granted = set(getattr(request.state, "permissions", []) or [])
        if requested - granted:
            raise HTTPException(
                status_code=403,
                detail={"code": 40301, "msg": "不能授予自己不具备的权限"},
            )

    old_role_code = role.role_code
    data = role_data.model_dump(exclude_unset=True)
    permission_ids = data.pop("permission_ids", None)
    for field, value in data.items():
        if value is not None:
            setattr(role, field, value)

    await _sync_role_permissions(role, permission_ids, db)
    if permission_ids is not None or role.role_code != old_role_code:
        await _bump_role_tokens(role.id, db)

    await db.commit()
    await db.refresh(role)
    return await _role_response(role, db)


@router.delete("/{role_id}", dependencies=[Depends(PermissionChecker("role:delete"))])
@audit_action("role_delete", module="roles", target_id_kwarg="role_id")
async def delete_role(
    request: Request,
    role_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Role).where(Role.id == UUID(role_id), Role.is_deleted.is_(False))
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "角色不存在"})
    if role.role_code == "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": 40301, "msg": "不能删除管理员角色"},
        )
    actor_role_id = await _actor_role_id(request, db)
    if actor_role_id == role.id:
        raise HTTPException(
            status_code=403,
            detail={"code": 40301, "msg": "不能删除自己所属的角色"},
        )

    role.is_deleted = True
    await _bump_role_tokens(role.id, db)
    await db.commit()
    return {"code": 200, "msg": "success"}
