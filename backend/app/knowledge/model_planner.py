from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select

from app.adapters.none import NoneAdapter
from app.core.config import settings
from app.knowledge.planner import Planner, QueryPlan
from app.knowledge.policy import ToolAuthorizationPolicy, get_tool_authorization_policy
from app.knowledge.schemas import KnowledgeQueryRequest
from app.models.product import Category

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 3


class ModelToolPlanner:
    """Lets the model select from a small, server-controlled set of read-only tools."""

    def __init__(
        self,
        fallback: Planner,
        registry,
        authz_policy: ToolAuthorizationPolicy | None = None,
    ) -> None:
        self.fallback = fallback
        self.registry = registry
        self.authz_policy = authz_policy or get_tool_authorization_policy()

    async def plan(
        self,
        request: KnowledgeQueryRequest,
        *,
        db,
        adapter,
        current_user: dict,
        permission_pool,
        session_id: str,
    ) -> QueryPlan:
        fallback = self.fallback.plan(request)
        if isinstance(adapter, NoneAdapter):
            return fallback

        allowed_tools = self._tools_for_user(permission_pool, current_user)
        if not allowed_tools:
            return fallback

        try:
            categories = await _category_context(db)
            response = await asyncio.wait_for(
                adapter.chat(
                    session_id=session_id,
                    message=_planning_request(request.message),
                    history=[],
                    system=_planning_instructions(categories, allowed_tools),
                    temperature=0,
                ),
                timeout=settings.AI_TOOL_PLANNING_TIMEOUT,
            )
            calls = _parse_tool_calls(response.get("answer"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("model_tool_planning_failed error_type=%s", type(exc).__name__)
            return fallback

        selected: list[str] = []
        params_by_tool: dict[str, dict] = {}
        for call in calls[:MAX_TOOL_CALLS]:
            name = call.get("name")
            arguments = call.get("arguments")
            if name not in allowed_tools:
                continue
            if not isinstance(arguments, dict) or name in params_by_tool:
                continue
            try:
                params_by_tool[name] = self.registry.validate_params(name, arguments)
            except Exception:  # noqa: BLE001
                continue
            selected.append(name)

        if not selected:
            return fallback
        return fallback.model_copy(
            update={
                "required_tools": selected,
                "tool_params": params_by_tool,
                "retrieval": {"enabled": True, "topics": fallback.entities.keywords[:5]},
            }
        )

    def _tools_for_user(self, permission_pool, current_user: dict) -> set[str]:
        tools: set[str] = set()
        for name in sorted(permission_pool.allowed_tools & self.registry.names()):
            definition = self.registry.definition(name)
            authz = self.authz_policy.authorize(
                name, permission_pool, current_user, definition.required_permissions
            )
            if not authz.allowed:
                continue
            tools.add(name)
        return tools


async def _category_context(db) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Category.category_name, Category.level)
        .where(Category.is_deleted.is_(False))
        .order_by(Category.level, Category.sort, Category.category_name)
        .limit(200)
    )
    return [dict(row._mapping) for row in result.all()]


def _parse_tool_calls(answer: str | None) -> list[dict[str, Any]]:
    text = (answer or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        calls = payload.get("tool_calls")
        if isinstance(calls, list):
            return [call for call in calls if isinstance(call, dict)]
    return []


def _planning_instructions(categories: list[dict[str, Any]], allowed_tools: set[str]) -> str:
    return (
        "你是 RiChangPIM 的只读工具规划器。理解用户完整自然语言，并选择查询所需的工具。"
        "仅输出合法 JSON，不要输出解释："
        "{\"tool_calls\":[{\"name\":\"工具名\",\"arguments\":{...}}]}。"
        "只能从可用工具选择，不能编造工具，不能执行写操作。用户要求最便宜时 sort_order 用 asc，"
        "最贵时用 desc；最长时 sort_by 用 specification_length 且 sort_order 用 desc；"
        "最短时 sort_order 用 asc。当前产品、价格、库存和规格问题使用 product.search。"
        "product.search 参数：keywords(string数组)、product_nos(string数组)、filters(object)、"
        "sort_by(face_price 或 specification_length)、sort_order(asc 或 desc)、limit(1-100)。"
        "product.get_many/product.compare 参数：product_ids(string数组) "
        "或 product_nos(string数组)。"
        "quality.summary 无参数；quality.list_issues 参数：issue_types(string数组)、limit(1-50)。"
        "supplier.compare 参数：product_ids(string数组) 或 product_nos(string数组)。"
        f"\n可用工具：{sorted(allowed_tools)}"
        f"\n可见品类（name 和 level）：{categories}"
    )


def _planning_request(message: str) -> str:
    return (
        "不要回答下列用户请求。只输出工具计划 JSON，格式为 "
        '{"tool_calls":[{"name":"工具名","arguments":{...}}]}。'
        f"\n待处理用户请求：{message}"
    )
