from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.security import get_password_hash
from app.middleware.audit import audit_action
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter()


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
    result = await db.execute(
        select(User).where(User.username == user_data.username, User.is_deleted.is_(False))
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail={"code": 40901, "msg": "用户名已存在"})

    user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        email=user_data.email,
        phone=user_data.phone,
        role_id=user_data.role_id,
    )
    db.add(user)
    await db.commit()
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
