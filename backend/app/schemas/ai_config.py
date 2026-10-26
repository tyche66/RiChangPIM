"""AI 配置中心 schemas（HLD §12：禁止散落字符串，读写契约集中在此）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AiConfigRead(BaseModel):
    scope: str
    label: str
    api_url: str | None = None
    api_key_masked: str | None = None
    has_api_key: bool = False
    chat_model: str | None = None
    chat_models: list[str] = Field(default_factory=list)
    embedding_model: str | None = None
    embedding_api_url: str | None = None
    embedding_api_key_masked: str | None = None
    timeout_seconds: float | None = None
    enabled: bool = True
    source: str = "env"


class AiConfigUpdate(BaseModel):
    """局部更新：``None`` 表示该字段保持不变（含"不改密钥"）。"""

    model_config = ConfigDict(extra="forbid")

    api_url: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=4096)
    chat_model: str | None = Field(default=None, max_length=128)
    chat_models: list[str] | None = None
    embedding_model: str | None = Field(default=None, max_length=128)
    embedding_api_url: str | None = Field(default=None, max_length=512)
    embedding_api_key: str | None = Field(default=None, max_length=4096)
    timeout_seconds: float | None = Field(default=None, gt=0, le=3600)
    enabled: bool | None = None


class AiConfigTestResult(BaseModel):
    scope: str
    ok: bool
    model: str | None = None
    latency_ms: int | None = None
    detail: str | None = None
