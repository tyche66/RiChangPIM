import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge.model_planner import ModelToolPlanner
from app.knowledge.permission_pool import POOL_ADMIN
from app.knowledge.planner import RuleBasedPlanner
from app.knowledge.schemas import KnowledgeQueryRequest
from app.knowledge.tools.registry import default_tool_registry


class _Result:
    def all(self):
        return []


@pytest.mark.anyio
async def test_model_planner_uses_valid_product_search_call():
    adapter = MagicMock()
    adapter.chat = AsyncMock(
        return_value={
            "answer": (
                '{"tool_calls":[{"name":"product.search","arguments":'
                '{"keywords":["办公桌"],"sort_by":"face_price",'
                '"sort_order":"asc","limit":1}}]}'
            )
        }
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())
    planner = ModelToolPlanner(RuleBasedPlanner(), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="最便宜的办公桌"),
        db=db,
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-1",
    )

    assert plan.required_tools == ["product.search"]
    assert plan.tool_params["product.search"]["sort_order"] == "asc"
    assert plan.retrieval["enabled"] is True
    assert "product.search" in adapter.chat.await_args.kwargs["system"]
    assert "待处理用户请求" in adapter.chat.await_args.kwargs["message"]


@pytest.mark.anyio
async def test_model_planner_drops_unknown_tool_and_falls_back():
    adapter = MagicMock()
    adapter.chat = AsyncMock(
        return_value={"answer": '{"tool_calls":[{"name":"sql.execute","arguments":{}}]}' }
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())
    planner = ModelToolPlanner(RuleBasedPlanner(), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="最便宜的办公桌"),
        db=db,
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-1",
    )

    assert plan.required_tools == ["product.search"]
    assert plan.tool_params == {}


@pytest.mark.anyio
async def test_model_planner_falls_back_when_model_times_out(monkeypatch):
    async def slow_chat(**kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr("app.knowledge.model_planner.settings.AI_TOOL_PLANNING_TIMEOUT", 0.01)
    adapter = MagicMock()
    adapter.chat = slow_chat
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())
    planner = ModelToolPlanner(RuleBasedPlanner(), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="最便宜的洽谈桌"),
        db=db,
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-1",
    )

    assert plan.required_tools == ["product.search"]
