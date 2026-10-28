import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.none import NoneAdapter
from app.knowledge.attributes import (
    AttributeDefinitionView,
    AttributeDictionary,
)
from app.knowledge.model_planner import ModelToolPlanner, _planning_instructions
from app.knowledge.permission_pool import POOL_ADMIN
from app.knowledge.planner import RuleBasedPlanner
from app.knowledge.schemas import KnowledgeQueryRequest
from app.knowledge.tools.registry import default_tool_registry


class _Result:
    def all(self):
        return []


class _ScalarResult:
    def all(self):
        return []


class _MappingResult:
    """同时满足 ``_category_context``（``result.all()``）与
    ``await_load_dictionary``（``result.scalars().all()``）。"""

    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return self._rows

    def scalars(self):
        return _ScalarResult()


def _db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_MappingResult())
    return db


def _dictionary() -> AttributeDictionary:
    """测试用属性词典：与生产同构（桌形/类目/颜色/面价/长度），但不连库。"""
    definitions = {
        "shape": AttributeDefinitionView(
            code="shape", name="桌形", data_type="option",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "category": AttributeDefinitionView(
            code="category", name="类目", data_type="option",
            multi_value=True, searchable=True, hard_filterable=True,
        ),
        "color": AttributeDefinitionView(
            code="color", name="颜色", data_type="option",
            multi_value=True, searchable=True, hard_filterable=True,
        ),
        "face_price": AttributeDefinitionView(
            code="face_price", name="面价", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "specification_length_mm": AttributeDefinitionView(
            code="specification_length_mm", name="长度", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
    }
    from app.knowledge.attributes import AliasEntry

    aliases = [
        AliasEntry(attribute_code="shape", option_code="arc", alias="弧形", normalized="弧形"),
        AliasEntry(attribute_code="shape", option_code="arc", alias="弧型", normalized="弧型"),
        AliasEntry(attribute_code="shape", option_code="arc", alias="圆弧", normalized="圆弧"),
        AliasEntry(attribute_code="shape", option_code="rect", alias="矩形", normalized="矩形"),
        AliasEntry(
            attribute_code="category", option_code="会议桌",
            alias="会议桌", normalized="会议桌",
        ),
        AliasEntry(
            attribute_code="category", option_code="会议桌",
            alias="会议台", normalized="会议台",
        ),
        AliasEntry(
            attribute_code="category", option_code="办公桌",
            alias="办公桌", normalized="办公桌",
        ),
        AliasEntry(
            attribute_code="category", option_code="洽谈桌",
            alias="洽谈桌", normalized="洽谈桌",
        ),
        AliasEntry(attribute_code="color", option_code="black", alias="黑色", normalized="黑色"),
        AliasEntry(attribute_code="color", option_code="white", alias="白色", normalized="白色"),
    ]
    return AttributeDictionary(definitions=definitions, aliases=aliases)


def test_model_planning_prompt_describes_typed_attribute_facets():
    prompt = _planning_instructions([], {"product.search"}, _dictionary())

    assert "hard_facets" in prompt
    assert "不同属性之间必须同时满足（AND）" in prompt
    assert "只能使用下列已定义的属性与取值，不得编造 attribute_code 或 option" in prompt
    assert "确实没有任何属性可归的词才放 unknown_terms" in prompt
    assert "不得拼成一个整体关键词" in prompt
    # 自然语言说法必须按语义归到已定义取值：2026-10-28「现代风格」返回空的根因
    assert "偏现代风格" in prompt
    assert "style=modern" in prompt
    assert "多字少字" in prompt
    # 不再宣称 shape 来自 tag_type
    assert "tag_type" not in prompt


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
    planner = ModelToolPlanner(RuleBasedPlanner(_dictionary()), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="最便宜的办公桌"),
        db=_db(),
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-1",
    )

    assert plan.required_tools == ["product.search"]
    assert plan.tool_params["product.search"]["sort_order"] == "asc"
    assert "product.search" in adapter.chat.await_args.kwargs["system"]
    assert "待处理用户请求" in adapter.chat.await_args.kwargs["message"]


@pytest.mark.anyio
async def test_model_product_search_cannot_discard_rule_facets():
    """规则解析出的硬条件优先级高于模型条件：模型不能覆盖/删除/放宽。"""
    adapter = MagicMock()
    adapter.chat = AsyncMock(
        return_value={
            "answer": (
                '{"tool_calls":[{"name":"product.search","arguments":'
                '{"keywords":["弧形会议桌"],"keyword":"弧形",'
                '"hard_facets":[{"attribute_code":"category","values":["办公桌"]},'
                '{"attribute_code":"shape","values":["rect"]}],'
                '"filters":{"keyword":"会议桌"}}}]}'
            )
        }
    )
    planner = ModelToolPlanner(RuleBasedPlanner(_dictionary()), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="弧形会议桌"),
        db=_db(),
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-shape",
    )

    params = plan.tool_params["product.search"]
    # 模型无法把 shape 从 arc 放宽成 rect，也无法丢掉 category
    assert params["facets"]["shape"] == ["arc"]
    assert "rect" not in params["facets"]["shape"]
    assert params["keyword"] is None
    assert "keyword" not in params["filters"]


@pytest.mark.anyio
async def test_model_returning_unknown_attribute_is_discarded():
    """模型返回字典里不存在的 attribute_code / option 必须被丢弃。"""
    adapter = MagicMock()
    adapter.chat = AsyncMock(
        return_value={
            "answer": (
                '{"tool_calls":[{"name":"product.search","arguments":'
                '{"hard_facets":[{"attribute_code":"invented_dimension","values":["x"]},'
                '{"attribute_code":"shape","values":["not_a_real_option"]},'
                '{"attribute_code":"color","values":["black"]}],"soft_terms":["弧形"]}}]}'
            )
        }
    )
    planner = ModelToolPlanner(RuleBasedPlanner(_dictionary()), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="弧形黑色会议桌"),
        db=_db(),
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-unknown-attr",
    )

    params = plan.tool_params["product.search"]
    codes = {f["attribute_code"] for f in params["hard_facets"]}
    assert "invented_dimension" not in codes
    # shape 的非法取值不产生硬条件；颜色（词典有 black 选项但无 alias）不进入
    assert "not_a_real_option" not in str(params)


@pytest.mark.anyio
async def test_model_tool_selection_cannot_bypass_hard_facets():
    adapter = MagicMock()
    adapter.chat = AsyncMock(
        return_value={
            "answer": '{"tool_calls":[{"name":"quality.summary","arguments":{}}]}'
        }
    )
    planner = ModelToolPlanner(RuleBasedPlanner(_dictionary()), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="弧形会议桌"),
        db=_db(),
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
        return_value={
            "answer": '{"tool_calls":[{"name":"sql.execute","arguments":{}}]}'
        }
    )
    planner = ModelToolPlanner(RuleBasedPlanner(_dictionary()), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="最便宜的办公桌"),
        db=_db(),
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
    planner = ModelToolPlanner(RuleBasedPlanner(_dictionary()), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="最便宜的洽谈桌"),
        db=_db(),
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
    planner = ModelToolPlanner(RuleBasedPlanner(_dictionary()), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="弧形会议桌"),
        db=_db(),
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-shape-timeout",
    )

    assert plan.required_tools == ["product.search"]
    facets = plan.entities.facets.model_dump()
    assert facets["values"]["shape"] == ["arc"]
    assert facets["values"]["category"] == ["会议桌"]


@pytest.mark.anyio
async def test_shape_facets_survive_when_model_planning_is_unavailable():
    plan = await ModelToolPlanner(
        RuleBasedPlanner(_dictionary()), default_tool_registry()
    ).plan(
        KnowledgeQueryRequest(message="弧形会议桌"),
        db=MagicMock(),
        adapter=NoneAdapter(),
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-shape-disabled",
    )

    assert plan.required_tools == ["product.search"]
    facets = plan.entities.facets.model_dump()
    assert facets["values"]["shape"] == ["arc"]
    assert facets["values"]["category"] == ["会议桌"]


@pytest.mark.anyio
async def test_model_returns_illegal_json_falls_back_to_rule_facets():
    adapter = MagicMock()
    adapter.chat = AsyncMock(return_value={"answer": "这不是 JSON"})
    planner = ModelToolPlanner(RuleBasedPlanner(_dictionary()), default_tool_registry())

    plan = await planner.plan(
        KnowledgeQueryRequest(message="弧形会议桌"),
        db=_db(),
        adapter=adapter,
        current_user={"role_code": "admin", "perms": []},
        permission_pool=POOL_ADMIN,
        session_id="session-illegal-json",
    )

    assert plan.required_tools == ["product.search"]
    assert plan.entities.facets.shape == ["arc"]
