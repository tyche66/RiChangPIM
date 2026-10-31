"""向量索引管理 schemas（读写契约集中在此，禁止散落字符串）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.knowledge_index_admin import RUN_NOW_HARD_CAP


class KnowledgeIndexSettingRead(BaseModel):
    enabled: bool
    timezone: str
    window_start: str
    window_end: str
    safety_cutoff_minutes: int
    reconcile_batch_size: int
    embedding_batch_size: int
    request_interval_seconds: int
    request_timeout_seconds: int
    max_attempts: int
    backoff_base_seconds: int
    backoff_max_seconds: int
    dead_retention_days: int
    stale_lock_minutes: int
    run_now_max_products: int = RUN_NOW_HARD_CAP
    run_now_max_duration_seconds: int


class KnowledgeIndexSettingUpdate(BaseModel):
    """局部更新：``None`` 表示该字段保持不变。

    ``run_now_max_products`` 是后端硬上限，**只读**：即使传了也会被忽略，
    以模型层 CheckConstraint + 这里的一致性双保险。
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    timezone: str | None = Field(default=None, max_length=64)
    window_start: str | None = Field(default=None, max_length=5)
    window_end: str | None = Field(default=None, max_length=5)
    safety_cutoff_minutes: int | None = Field(default=None, ge=0, le=30)
    reconcile_batch_size: int | None = Field(default=None, ge=1, le=1000)
    embedding_batch_size: int | None = Field(default=None, ge=1, le=96)
    request_interval_seconds: int | None = Field(default=None, ge=0, le=300)
    request_timeout_seconds: int | None = Field(default=None, ge=10, le=600)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    backoff_base_seconds: int | None = Field(default=None, ge=5, le=3600)
    backoff_max_seconds: int | None = Field(default=None, ge=30, le=21600)
    dead_retention_days: int | None = Field(default=None, ge=7, le=3650)
    stale_lock_minutes: int | None = Field(default=None, ge=5, le=240)
    run_now_max_duration_seconds: int | None = Field(default=None, ge=60, le=3600)

    @field_validator("window_start", "window_end")
    @classmethod
    def _check_hhmm(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = value.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError("时间格式必须为 HH:MM")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("时间超出 00:00-23:59 范围")
        return f"{hour:02d}:{minute:02d}"


class JobResetRequest(BaseModel):
    """授权的失败任务重置：按 job_id 精确重置，或按状态批量（≤200）。"""

    model_config = ConfigDict(extra="forbid")

    job_ids: list[str] | None = None
    scope: str | None = None  # dead | failed
    limit: int = Field(default=200, ge=1, le=200)
