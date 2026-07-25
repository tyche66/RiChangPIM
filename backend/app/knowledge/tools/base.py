from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class ToolContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    db: Any
    current_user: dict
    permission_pool: Any
    trace_id: str


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str
    description: str
    input_schema: type[BaseModel]
    required_permissions: set[str]
    risk_level: str
    read_only: bool
    max_results: int
    timeout_ms: int
    field_projection: bool
    audit_event: str


@runtime_checkable
class KnowledgeTool(Protocol):
    definition: ToolDefinition
    async def run(self, params: BaseModel, context: ToolContext) -> dict[str, Any]: ...
