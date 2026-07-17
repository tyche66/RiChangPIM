from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OperationLogResponse(BaseModel):
    id: UUID
    user_id: UUID | None = None
    module: str
    action: str
    target_id: UUID | None = None
    response_code: int
    ip: str | None = None
    operate_time: datetime

    model_config = ConfigDict(from_attributes=True)
