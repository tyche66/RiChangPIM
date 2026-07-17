from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.permission import get_current_user
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from app.middleware.audit import audit_action
from app.models.user import Permission, Role, RolePermission, User
from app.schemas.user import LoginRequest, UserResponse

router = APIRouter()


async def _load_role_and_user(user_id, db: AsyncSession):
    result = await db.execute(
        select(User, Role.role_code)
        .join(Role, Role.id == User.role_id)
        .where(User.id == user_id, User.is_deleted.is_(False))
    )
    row = result.first()
    if not row:
        return None, None, []
    u, role_code = row
    perm_result = await db.execute(
        select(Permission.perm_code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(
            RolePermission.role_id == u.role_id,
            Permission.is_deleted.is_(False),
            RolePermission.is_deleted.is_(False),
        )
    )
    perms: list[str] = [r.perm_code for r in perm_result.fetchall()]
    return u, role_code, perms


@router.post("/login")
@audit_action("login", module="auth", failed_action="login_failed")
async def login(request: Request, login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.username == login_data.username, User.is_deleted.is_(False))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40101, "msg": "用户名或密码错误"},
        )

    _, role_code, perms = await _load_role_and_user(user.id, db)

    request.state.user_id = str(user.id)

    access_token = create_access_token(
        data={"sub": str(user.id), "role_code": role_code, "perms": perms},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_access_token(
        data={"sub": str(user.id), "type": "refresh"},
        expires_delta=timedelta(days=7),
    )
    return {
        "code": 200,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        },
    }


@router.post("/refresh")
async def refresh_token_endpoint(refresh_token: str, db: AsyncSession = Depends(get_db)):
    payload = decode_access_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40102, "msg": "Refresh token 无效"},
        )
    user_id = UUID(payload["sub"])
    _, role_code, perms = await _load_role_and_user(user_id, db)
    if role_code is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40103, "msg": "用户不存在"},
        )
    new_access = create_access_token(
        data={"sub": payload["sub"], "role_code": role_code, "perms": perms},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    new_refresh = create_access_token(
        data={"sub": payload["sub"], "type": "refresh"},
        expires_delta=timedelta(days=7),
    )
    return {
        "code": 200,
        "data": {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        },
    }


@router.post("/logout")
@audit_action("logout", module="auth")
async def logout(request: Request):
    return {"code": 200, "msg": "success"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(current_user["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "用户不存在"})
    return user


@router.post("/change-password")
@audit_action("change_password", module="auth")
async def change_password(
    request: Request,
    old_password: str,
    new_password: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(current_user["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user or not verify_password(old_password, user.password_hash):
        raise HTTPException(status_code=400, detail={"code": 40001, "msg": "原密码错误"})
    user.password_hash = get_password_hash(new_password)
    await db.commit()
    return {"code": 200, "msg": "success"}
