from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.adapters.none import NoneAdapter
from app.knowledge.events import sse_event
from app.knowledge.gateway import _deterministic_answer
from app.knowledge.model_gateway import AdapterModelGateway
from app.knowledge.permission_pool import RoleBasedPoolResolver
from app.knowledge.planner import RuleBasedPlanner
from app.knowledge.schemas import KnowledgeQueryRequest, KnowledgeQueryResponse
from app.knowledge.tools.registry import default_tool_registry


def test_query_schema_rejects_long_message():
    with pytest.raises(ValidationError):
        KnowledgeQueryRequest(message="x" * 4001)


def test_query_schema_rejects_unknown_filter():
    with pytest.raises(ValidationError):
        KnowledgeQueryRequest(message="查产品", scope={"filters": {"role": "admin"}})


def test_query_schema_rejects_client_role():
    with pytest.raises(ValidationError):
        KnowledgeQueryRequest(message="查产品", role="admin")


def test_sse_event_format_is_single_line_json():
    frame = sse_event("meta", {"schema_version": "1.0", "trace_id": "t1", "session_id": "s1"})
    assert frame.startswith("event: meta\n")
    data_line = frame.splitlines()[1]
    assert data_line.startswith("data: ")
    assert json.loads(data_line.removeprefix("data: "))["trace_id"] == "t1"


def test_non_stream_response_contract_defaults():
    response = KnowledgeQueryResponse(trace_id="t1", session_id="s1", answer="ok")
    data = response.model_dump(mode="json")
    assert set(data) == {
        "trace_id",
        "session_id",
        "answer",
        "facts",
        "sources",
        "products",
        "pending_actions",
        "confidence",
        "insufficient_sources",
        "usage",
    }
    assert data["pending_actions"] == []


def test_planner_compare_and_security():
    planner = RuleBasedPlanner()
    plan = planner.plan(KnowledgeQueryRequest(message="比较 A100 和 A200 区别"))
    assert plan.intent == "product_compare"
    assert "product.compare" in plan.required_tools
    slash_dot = planner.plan(KnowledgeQueryRequest(message="查 EMD86L/R.200170 规格"))
    assert "EMD86L/R.200170" in slash_dot.entities.product_nos
    blocked = planner.plan(KnowledgeQueryRequest(message="帮我执行 SQL select * from user"))
    assert blocked.intent == "unsupported"
    draft = planner.plan(KnowledgeQueryRequest(message="请创建方案草稿 A100"))
    assert draft.intent == "proposal_draft"
    procurement = planner.plan(KnowledgeQueryRequest(message="采购比较供应商 A100 交期"))
    assert procurement.intent == "procurement_compare"


def test_planner_extracts_chinese_product_search_terms_and_price_sort():
    planner = RuleBasedPlanner()
    plan = planner.plan(KnowledgeQueryRequest(message="找出最便宜的铭达办公桌"))

    assert plan.intent == "product_search"
    assert plan.entities.keywords == ["铭达", "办公桌"]


def test_planner_extracts_unknown_short_category_as_fallback_search_term():
    plan = RuleBasedPlanner().plan(KnowledgeQueryRequest(message="最便宜的洽谈桌"))

    assert plan.entities.keywords == ["洽谈桌"]
    assert plan.required_tools == ["product.search"]
    assert plan.entities.price_sort == "asc"


def test_planner_routes_natural_language_to_knowledge_retrieval():
    plan = RuleBasedPlanner().plan(
        KnowledgeQueryRequest(message="二十人会议室需要怎样配置桌椅，空间利用率会更好？")
    )

    assert plan.intent == "knowledge_question"
    assert plan.retrieval["enabled"] is True
    assert plan.required_tools == []


def test_price_sorted_products_return_the_cheapest_product():
    plan = RuleBasedPlanner().plan(KnowledgeQueryRequest(message="最便宜的办公桌"))
    answer = _deterministic_answer(
        plan,
        facts=[],
        products=[{"product_name": "铭达洽谈桌 EMD70.095095", "face_price_display": 3130}],
        sources=[],
        issues=[],
        suppliers=[],
        pending_actions=[],
    )

    assert answer == "当前最低面价为 铭达洽谈桌 EMD70.095095，面价 3130。"


def test_price_sorted_products_return_the_most_expensive_product():
    plan = RuleBasedPlanner().plan(KnowledgeQueryRequest(message="最贵的会议桌"))
    answer = _deterministic_answer(
        plan,
        facts=[],
        products=[{"product_name": "铭达会议桌 EMD78.480160", "face_price_display": 16810}],
        sources=[],
        issues=[],
        suppliers=[],
        pending_actions=[],
    )

    assert plan.entities.price_sort == "desc"
    assert answer == "当前最高面价为 铭达会议桌 EMD78.480160，面价 16810。"


def test_planner_and_answer_support_longest_product_specification():
    plan = RuleBasedPlanner().plan(KnowledgeQueryRequest(message="最长的桌子"))
    answer = _deterministic_answer(
        plan,
        facts=[],
        products=[
            {
                "product_name": "铭达会议桌 EMD78.480160",
                "specification_length_mm": 4800,
            }
        ],
        sources=[],
        issues=[],
        suppliers=[],
        pending_actions=[],
    )

    assert plan.entities.keywords == ["桌子"]
    assert plan.entities.specification_sort == "desc"
    assert answer == "当前最长的产品为 铭达会议桌 EMD78.480160，长度 4800 mm。"


def test_permission_pool_projection_rules():
    pool = RoleBasedPoolResolver().resolve(
        {"role_code": "sales", "perms": ["ai:use", "product:view"]}
    )
    assert "product.compare" not in pool.allowed_tools
    assert "cost_price" in pool.hidden_fields
    admin = RoleBasedPoolResolver().resolve({"role_code": "admin", "perms": []})
    assert "product.compare" in admin.allowed_tools
    assert not admin.hidden_fields


def test_tool_registry_rejects_unknown_tool():
    registry = default_tool_registry()
    assert "product.search" in registry.names()
    assert "supplier.compare" in registry.names()


@pytest.mark.anyio
async def test_model_gateway_none_fail_closed():
    gateway = AdapterModelGateway(NoneAdapter())
    with pytest.raises(Exception) as exc:
        await gateway.generate_answer(session_id="s", message="hi", context={}, trace_id="t")
    assert exc.value.code.value == "CAPABILITY_DISABLED"
