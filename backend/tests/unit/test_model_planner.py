import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.none import NoneAdapter
from app.knowledge.model_planner import ModelToolPlanner, _planning_instructions
from app.knowledge.permission_pool import POOL_ADMIN
from app.knowledge.planner import RuleBasedPlanner
from app.knowledge.schemas import KnowledgeQueryRequest
from app.knowledge.tools.registry import default_tool_registry


class _Result:
    def all(self):
        return []


def test_model_planning_prompt_describes_typed_category_and_shape_facets():
    prompt = _planning_instructions([], {"product.search"})

    assert "facets(object，category(string数组)、shape(string数组))" in prompt
    assert "category 与 shape 条件必须同时满足（AND）" in prompt
    assert "shape 只能匹配 tag_type=shape 的标签" in prompt
    assert "不得改写为泛关键词或文本搜索条件" in prompt


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
async def test_model_product_search_cannot_discard_rule_facets():
    adapter = MagicMock()
    adapter.chat = AsyncMock(
        return_value={
            "answer": (
                '{"tool_calls":[{"name":"product.search","arguments":'
                '{"keywords":["弧形会议桌","8人"],"keyword":"弧形",'
                '"facets":{"category":["办公桌"],"shape":["矩形"]},'
                '"filters":{"keyword":"会议桌"}}}]} '
                .strip()
            )
        }
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())
    planner = ModelToolPlanner(RuleBasedPlanner(), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="弧形会议桌"),
        db=db,
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-shape",
    )

    params = plan.tool_params["product.search"]
    assert params["facets"] == {"category": ["会议桌"], "shape": ["弧形"]}
    assert params["keywords"] == ["8人"]
    assert params["keyword"] is None
    assert "keyword" not in params["filters"]


@pytest.mark.anyio
async def test_model_tool_selection_cannot_bypass_shape_search():
    adapter = MagicMock()
    adapter.chat = AsyncMock(
        return_value={
            "answer": '{"tool_calls":[{"name":"quality.summary","arguments":{}}]}'
        }
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())
    planner = ModelToolPlanner(RuleBasedPlanner(), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="弧形会议桌"),
        db=db,
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-shape-tool-selection",
    )

    assert plan.required_tools == ["product.search"]
    assert plan.tool_params == {}


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
    assert plan.entities.facets.shape == []


@pytest.mark.anyio
async def test_shape_facets_survive_model_timeout_fallback(monkeypatch):
    async def slow_chat(**kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr("app.knowledge.model_planner.settings.AI_TOOL_PLANNING_TIMEOUT", 0.01)
    adapter = MagicMock()
    adapter.chat = slow_chat
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())
    planner = ModelToolPlanner(RuleBasedPlanner(), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="弧形会议桌"),
        db=db,
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-shape-timeout",
    )

    assert plan.required_tools == ["product.search"]
    assert plan.entities.facets.model_dump() == {"category": ["会议桌"], "shape": ["弧形"]}
    assert plan.retrieval["enabled"] is False


@pytest.mark.anyio
async def test_shape_facets_survive_when_model_planning_is_unavailable():
    plan = await ModelToolPlanner(RuleBasedPlanner(), default_tool_registry()).plan(
        KnowledgeQueryRequest(message="弧形会议桌"),
        db=MagicMock(),
        adapter=NoneAdapter(),
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-shape-disabled",
    )

    assert plan.required_tools == ["product.search"]
    assert plan.entities.facets.model_dump() == {"category": ["会议桌"], "shape": ["弧形"]}
    assert plan.retrieval["enabled"] is False
