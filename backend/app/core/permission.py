from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

security = HTTPBearer(auto_error=False)

_SESSION_REVOKED = {"code": 40104, "msg": "登录状态已失效，请重新登录"}


async def ensure_token_version(payload: dict, db: AsyncSession) -> None:
    """校验 JWT 的 ``tv`` 声明与用户当前 ``token_version`` 一致。

    历史 token 没有 ``tv`` 声明（功能上线前签发），保持兼容放行，自然过期；
    上线后签发的 token 一律带 ``tv``，重设密码自增 ``token_version`` 即全部失效。
    """
    if "tv" not in payload:
        return
    try:
        user_id = UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_REVOKED
        ) from None

    result = await db.execute(
        select(User.token_version, User.is_deleted).where(User.id == user_id)
    )
    row = result.first()
    if row is None or row.is_deleted or row.token_version != payload["tv"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_REVOKED
        )


class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
        db: AsyncSession = Depends(get_db),
    ):
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": 40101, "msg": "未登录 / Token 无效"},
            )
        payload = decode_access_token(credentials.credentials)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": 40102, "msg": "Token 已过期"},
            )
        request.state.user_id = payload.get("sub")
        request.state.role_code = payload.get("role_code")
        request.state.permissions = payload.get("perms", [])

        # 权限判断先于版本查询：无权限时无需访问 DB，也保持既有的 403 语义。
        if (
            self.required_permission
            and request.state.role_code != "admin"
            and self.required_permission not in request.state.permissions
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 40301, "msg": "无权限访问该资源"},
            )

        await ensure_token_version(payload, db)
        return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40101, "msg": "未登录 / Token 无效"},
        )
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40102, "msg": "Token 已过期"},
        )
    await ensure_token_version(payload, db)
    return payload
