from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.adapters.base import AIServiceAdapter
from app.adapters.factory import get_ai_adapter
from app.core.config import settings
from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.knowledge.errors import KnowledgeGatewayError
from app.knowledge.gateway import KnowledgeGateway
from app.knowledge.schemas import KnowledgeQueryRequest
from app.middleware.audit import audit_action

router = APIRouter()


def _envelope(data, code: int = 200, msg: str = "success") -> dict:
    return {"code": code, "data": data, "msg": msg}


@router.post("/query")
@audit_action("knowledge_query", module="knowledge")
async def query(
    request: Request,
    current_user: dict = Depends(PermissionChecker("")),
    adapter: AIServiceAdapter = Depends(get_ai_adapter),
    db: AsyncSession = Depends(get_db),
):
    if not settings.KNOWLEDGE_GATEWAY_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={"code": "CAPABILITY_DISABLED", "msg": "Knowledge Gateway 已关闭", "retryable": False},
        )
    try:
        body = KnowledgeQueryRequest.model_validate(await request.json())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    gateway = KnowledgeGateway(db=db, adapter=adapter)
    if body.capabilities.stream:
        return StreamingResponse(
            gateway.stream(body, current_user),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        response = await gateway.handle(body, current_user)
        return _envelope(response.model_dump(mode="json"))
    except KnowledgeGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code.value, "msg": exc.message, "retryable": exc.retryable},
        ) from exc
