from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "code": 200,
        "data": {
            "status": "healthy",
            "components": {
                "db": "unknown",
                "redis": "unknown",
                "minio": "unknown",
            },
        },
    }


@router.get("/health/live")
async def liveness_check():
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_check(request: Request):
    from app.main import health_ready

    return await health_ready(request)
