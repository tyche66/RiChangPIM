from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError
from app.knowledge.field_projection import FieldProjectionStrategy, get_field_projection_strategy
from app.knowledge.metrics import record_tool
from app.knowledge.policy import ToolAuthorizationPolicy, get_tool_authorization_policy
from app.knowledge.tools.base import KnowledgeTool, ToolContext


class ToolRegistry:
    def __init__(
        self,
        *,
        authz_policy: ToolAuthorizationPolicy | None = None,
        projection: FieldProjectionStrategy | None = None,
    ) -> None:
        self._tools: dict[str, KnowledgeTool] = {}
        self.authz_policy = authz_policy or get_tool_authorization_policy()
        self.projection = projection or get_field_projection_strategy()

    def register(self, tool: KnowledgeTool) -> None:
        if not tool.definition.read_only:
            raise ValueError("P1 ToolRegistry only accepts read-only tools")
        self._tools[tool.definition.name] = tool

    def names(self) -> set[str]:
        return set(self._tools)

    def definition(self, name: str):
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(name)
        return tool.definition

    def validate_params(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        definition = self.definition(name)
        return definition.input_schema.model_validate(params).model_dump(mode="json")

    async def execute(
        self, name: str, params: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            raise KnowledgeGatewayError(
                KnowledgeErrorCode.PLAN_INVALID, f"未注册工具: {name}", status_code=400
            )
        authz = self.authz_policy.authorize(
            name,
            context.permission_pool,
            context.current_user,
            tool.definition.required_permissions,
        )
        if not authz.allowed:
            raise KnowledgeGatewayError(
                KnowledgeErrorCode.POLICY_BLOCKED, authz.reason or "工具权限不足", status_code=403
            )
        try:
            schema = tool.definition.input_schema
            parsed = schema.model_validate(params)
            start = time.perf_counter()
            result = await tool.run(parsed, context)
            if tool.definition.field_projection:
                result = self.projection.project(result, context.permission_pool)
            record_tool(
                trace_id=context.trace_id,
                tool=name,
                status="ok",
                latency_ms=int((time.perf_counter() - start) * 1000),
                result_count=_result_count(result),
            )
            return result
        except KnowledgeGatewayError:
            raise
        except Exception as exc:
            raise KnowledgeGatewayError(
                KnowledgeErrorCode.TOOL_FAILED, "只读工具执行失败", status_code=500
            ) from exc


class EmptyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


def default_tool_registry() -> ToolRegistry:
    from app.knowledge.tools.product import (
        ProductCompareTool,
        ProductGetManyTool,
        ProductSearchTool,
    )
    from app.knowledge.tools.quality import QualityListIssuesTool, QualitySummaryTool
    from app.knowledge.tools.supplier import SupplierCompareTool

    registry = ToolRegistry()
    registry.register(ProductSearchTool())
    registry.register(ProductGetManyTool())
    registry.register(ProductCompareTool())
    registry.register(QualitySummaryTool())
    registry.register(QualityListIssuesTool())
    registry.register(SupplierCompareTool())
    return registry


def _result_count(result: dict[str, Any]) -> int:
    for key in ("products", "suppliers", "issues", "facts"):
        value = result.get(key)
        if isinstance(value, list):
            return len(value)
    return 0
