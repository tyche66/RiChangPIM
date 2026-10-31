import logging
from datetime import UTC, datetime, timedelta
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
from app.core.security_limits import (
    check_login_allowed,
    clear_login_failures,
    get_client_ip,
    is_jti_revoked,
    record_login_failure,
    revoke_jti,
)
from app.middleware.audit import audit_action
from app.models.user import Permission, Role, RolePermission, User
from app.schemas.user import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    UserResponse,
)

logger = logging.getLogger("app.auth")

router = APIRouter()

_DUMMY_PASSWORD_HASH = get_password_hash("timing-only-dummy-password")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": 40101, "msg": "用户名或密码错误"},
    )


async def _load_role_and_user(user_id, db: AsyncSession):
    result = await db.execute(
        select(User, Role.role_code)
        .join(Role, Role.id == User.role_id)
        .where(
            User.id == user_id,
            User.is_deleted.is_(False),
            User.status == "active",
        )
    )
    row = result.first()
    if not row:
        return None, None, []
    u, role_code = row
    if role_code == "admin":
        perm_result = await db.execute(
            select(Permission.perm_code).where(Permission.is_deleted.is_(False))
        )
        perms: list[str] = [r.perm_code for r in perm_result.fetchall()]
        return u, role_code, perms

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
    client_ip = get_client_ip(request)
    allowed, retry_after = await check_login_allowed(login_data.username, client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": 42901, "msg": "登录尝试过于频繁，请稍后再试"},
            headers={"Retry-After": str(retry_after)},
        )

    result = await db.execute(
        select(User).where(User.username == login_data.username, User.is_deleted.is_(False))
    )
    user = result.scalar_one_or_none()
    if user is None:
        verify_password(login_data.password, _DUMMY_PASSWORD_HASH)
        await record_login_failure(login_data.username, client_ip)
        raise _unauthorized()

    password_ok = verify_password(login_data.password, user.password_hash)
    if not password_ok or user.status != "active":
        await record_login_failure(login_data.username, client_ip)
        raise _unauthorized()

    _, role_code, perms = await _load_role_and_user(user.id, db)
    if role_code is None:
        await record_login_failure(login_data.username, client_ip)
        raise _unauthorized()

    await clear_login_failures(login_data.username, client_ip)
    request.state.user_id = str(user.id)
    user_id = str(user.id)
    # commit/rollback 可能让 ORM 属性过期，先取出签发 token 需要的值。
    token_version = user.token_version or 0

    # 登录时间要真的落库，用户管理里的「最后登录」才不是空壳。
    # 写失败不能把已经通过校验的登录卡住，所以单独 try 一次并降级为日志。
    user.last_login_time = datetime.now(UTC)
    try:
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()
        # rollback expires ORM attributes; log the captured id instead of touching user.id here.
        logger.warning("last_login_time 写入失败 user_id=%s", user_id, exc_info=True)

    access_token = create_access_token(
        data={"sub": user_id, "role_code": role_code, "perms": perms, "tv": token_version},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_access_token(
        data={"sub": user_id, "tv": token_version},
        expires_delta=timedelta(days=7),
        token_type="refresh",
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
async def refresh_token_endpoint(
    payload_data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = decode_access_token(payload_data.refresh_token)
    if (
        not payload
        or payload.get("type") != "refresh"
        or not payload.get("jti")
        or "tv" not in payload
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40102, "msg": "Refresh token 无效"},
        )
    jti = str(payload["jti"])
    if await is_jti_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40104, "msg": "登录状态已失效，请重新登录"},
        )
    try:
        user_id = UUID(str(payload["sub"]))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40102, "msg": "Refresh token 无效"},
        ) from None
    user, role_code, perms = await _load_role_and_user(user_id, db)
    if role_code is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40103, "msg": "用户不存在"},
        )
    token_version = user.token_version or 0
    if payload["tv"] != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40104, "msg": "登录状态已失效，请重新登录"},
        )
    if not await revoke_jti(jti, int(payload.get("exp", 0))):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": 50301, "msg": "会话服务暂不可用，请稍后重试"},
        )
    new_access = create_access_token(
        data={"sub": payload["sub"], "role_code": role_code, "perms": perms, "tv": token_version},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    new_refresh = create_access_token(
        data={"sub": payload["sub"], "tv": token_version},
        expires_delta=timedelta(days=7),
        token_type="refresh",
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
async def logout(
    request: Request,
    payload: LogoutRequest | None = None,
    current_user: dict = Depends(get_current_user),
):
    if not await revoke_jti(str(current_user["jti"]), int(current_user.get("exp", 0))):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": 50301, "msg": "会话服务暂不可用，请稍后重试"},
        )
    if payload and payload.refresh_token:
        refresh_payload = decode_access_token(payload.refresh_token)
        if (
            refresh_payload
            and refresh_payload.get("type") == "refresh"
            and refresh_payload.get("sub") == current_user.get("sub")
            and refresh_payload.get("jti")
        ):
            await revoke_jti(
                str(refresh_payload["jti"]), int(refresh_payload.get("exp", 0))
            )
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
    payload_data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(current_user["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload_data.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail={"code": 40001, "msg": "原密码错误"})
    user.password_hash = get_password_hash(payload_data.new_password)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    return {"code": 200, "msg": "success"}
