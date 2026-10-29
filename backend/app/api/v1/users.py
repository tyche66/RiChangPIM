from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.security import get_password_hash
from app.middleware.audit import audit_action
from app.models.user import User
from app.schemas.user import ResetPasswordRequest, UserCreate, UserResponse, UserUpdate

router = APIRouter()

_USERNAME_TAKEN = {
    "code": 40901,
    # username 在库里是全局唯一（不是 partial index），软删除记录同样占用该名字。
    "msg": "用户名已被占用（含已删除用户），请更换用户名",
}


def _require_admin(request: Request) -> None:
    if getattr(request.state, "role_code", None) != "admin":
        raise HTTPException(
            status_code=403, detail={"code": 40301, "msg": "仅系统管理员可重设用户密码"}
        )


@router.get(
    "",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("user:view"))],
)
async def list_users(
    role_id: UUID | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).where(User.is_deleted.is_(False))
    if role_id:
        query = query.where(User.role_id == role_id)
    if status:
        query = query.where(User.status == status)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "code": 200,
        "data": {
            "list": [UserResponse.model_validate(u) for u in users],
            "total": total,
            "page": page,
            "size": size,
        },
    }


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(PermissionChecker("user:view"))],
)
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "用户不存在"})
    return user


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker("user:create"))],
)
@audit_action("user_create", module="users", target_id_kwarg="id")
async def create_user(request: Request, user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # 不加 is_deleted 过滤：软删除用户仍占用用户名，不能自动恢复或复用。
    result = await db.execute(
        select(User.id).where(User.username == user_data.username).limit(1)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=_USERNAME_TAKEN)

    user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        email=user_data.email,
        phone=user_data.phone,
        role_id=user_data.role_id,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # 并发创建时唯一约束是最后一道闸门，兜底成 409 而不是 500。
        await db.rollback()
        raise HTTPException(status_code=409, detail=_USERNAME_TAKEN) from None
    await db.refresh(user)
    return user


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(PermissionChecker("user:edit"))],
)
async def update_user(user_id: UUID, user_data: UserUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "用户不存在"})

    for field, value in user_data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/{user_id}/disable",
    response_model=UserResponse,
    dependencies=[Depends(PermissionChecker("user:disable"))],
)
@audit_action("user_disable", module="users", target_id_kwarg="user_id")
async def disable_user(request: Request, user_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "用户不存在"})
    if user.status == "disabled":
        return user

    user.status = "disabled"
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/{user_id}/reset-password",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("user:edit"))],
)
@audit_action("user_password_reset", module="users", target_id_kwarg="user_id")
async def reset_password(
    request: Request,
    user_id: UUID,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    # user:edit 只说明能编辑用户；重设密码额外要求系统管理员角色。
    _require_admin(request)

    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "用户不存在"})

    user.password_hash = get_password_hash(payload.new_password)
    # 旧 JWT 的 tv 与新版本不一致后，鉴权层会直接拒绝。
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    return {"code": 200, "msg": "密码已重设，该用户需重新登录"}


@router.delete("/{user_id}", dependencies=[Depends(PermissionChecker("user:delete"))])
@audit_action("user_delete", module="users")
async def delete_user(request: Request, user_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "用户不存在"})

    user.is_deleted = True
    await db.commit()
    return {"code": 200, "msg": "success"}
