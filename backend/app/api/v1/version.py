from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.permission import PermissionChecker

router = APIRouter()


@router.get("/version", dependencies=[Depends(PermissionChecker("stats:view"))])
async def get_version():
    """后端自己这一份构建指纹。

    这里**只报后端**。原来还返回过一个 `frontend_version`，值直接抄的
    `backend_version` —— 前端根本不是这么部署的（`frontend/dist` 可以是任意一次
    独立构建），所以那个字段是后端在替前端说谎：前后端真的不同版时它照样显示一致。

    真正的前端版本由前端自己在构建期注入（`frontend/src/config/version.ts` 读
    `VITE_APP_VERSION` / `VITE_BUILD_ID` / `VITE_GIT_COMMIT`，缺省回落到
    `frontend/package.json`），一致性由 `compareBuilds()` 在浏览器里比对本地构建值和
    这个接口返回的后端值得出。后端凭空补一个前端版本只会把那个比对变成永远相等。
    """
    backend_version = settings.APP_VERSION or settings.VERSION
    return {
        "code": 200,
        "data": {
            "app_name": settings.APP_NAME,
            "backend_version": backend_version,
            "build_id": settings.BUILD_ID or "dev-local",
            "git_commit": settings.GIT_COMMIT or "unknown",
            "build_time": settings.BUILD_TIME or "unknown",
            "environment": settings.APP_ENV or "development",
            "api_version": "v1",
        },
    }
