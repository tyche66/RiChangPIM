from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OperationLogResponse(BaseModel):
    id: UUID
    user_id: UUID | None = None
    # 写入时定格的操作人用户名；取不到就是 None，前端退化显示用户编号。
    username: str | None = None
    module: str
    action: str
    target_id: UUID | None = None
    response_code: int
    ip: str | None = None
    operate_time: datetime

    model_config = ConfigDict(from_attributes=True)
