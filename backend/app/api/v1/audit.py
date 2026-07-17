from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.models.audit import OperationLog
from app.schemas.audit import OperationLogResponse

router = APIRouter()


@router.get("/operation-logs", response_model=dict)
async def list_operation_logs(
    action: str | None = None,
    module: str | None = None,
    user_id: UUID | None = None,
    response_code: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: dict = Depends(PermissionChecker("audit:view")),
):
    stmt = select(OperationLog)
    if action:
        stmt = stmt.where(OperationLog.action == action)
    if module:
        stmt = stmt.where(OperationLog.module == module)
    if user_id:
        stmt = stmt.where(OperationLog.user_id == user_id)
    if response_code is not None:
        stmt = stmt.where(OperationLog.response_code == response_code)
    if start_time:
        stmt = stmt.where(OperationLog.operate_time >= start_time)
    if end_time:
        stmt = stmt.where(OperationLog.operate_time <= end_time)

    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()

    stmt = stmt.order_by(OperationLog.operate_time.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "code": 200,
        "data": {
            "list": [
                OperationLogResponse.model_validate(row).model_dump(mode="json")
                for row in rows
            ],
            "total": total,
            "page": page,
            "size": size,
        },
    }
