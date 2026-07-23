from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token

security = HTTPBearer(auto_error=False)


class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(
        self, request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)
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

        if (
            self.required_permission
            and request.state.role_code != "admin"
            and self.required_permission not in request.state.permissions
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 40301, "msg": "无权限访问该资源"},
            )
        return payload


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
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
    return payload
