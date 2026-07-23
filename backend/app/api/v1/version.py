from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.permission import PermissionChecker

router = APIRouter()


@router.get("/version", dependencies=[Depends(PermissionChecker("stats:view"))])
async def get_version():
    backend_version = settings.APP_VERSION or settings.VERSION
    return {
        "code": 200,
        "data": {
            "app_name": settings.APP_NAME,
            "backend_version": backend_version,
            "frontend_version": backend_version,
            "build_id": settings.BUILD_ID or "dev-local",
            "git_commit": settings.GIT_COMMIT or "unknown",
            "build_time": settings.BUILD_TIME or "unknown",
            "environment": settings.APP_ENV or "development",
            "api_version": "v1",
        },
    }
