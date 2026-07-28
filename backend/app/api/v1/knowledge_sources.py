from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.knowledge.errors import KnowledgeGatewayError
from app.knowledge.source_resolver import SourceResolver

router = APIRouter()


@router.get("/sources/{source_id}")
async def get_source(
    source_id: str,
    current_user: dict = Depends(PermissionChecker("")),
    db: AsyncSession = Depends(get_db),
):
    try:
        source = await SourceResolver(db).resolve(source_id, current_user)
        return {"code": 200, "data": source.model_dump(mode="json"), "msg": "success"}
    except KnowledgeGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code.value, "msg": exc.message, "retryable": exc.retryable},
        ) from exc
