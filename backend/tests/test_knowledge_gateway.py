from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.adapters.none import NoneAdapter
from app.knowledge.events import sse_event
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
    blocked = planner.plan(KnowledgeQueryRequest(message="帮我执行 SQL select * from user"))
    assert blocked.intent == "unsupported"


def test_permission_pool_projection_rules():
    pool = RoleBasedPoolResolver().resolve({"role_code": "sales", "perms": ["ai:use", "product:view"]})
    assert "product.compare" not in pool.allowed_tools
    assert "cost_price" in pool.hidden_fields
    admin = RoleBasedPoolResolver().resolve({"role_code": "admin", "perms": []})
    assert "product.compare" in admin.allowed_tools
    assert not admin.hidden_fields


def test_tool_registry_rejects_unknown_tool():
    registry = default_tool_registry()
    assert "product.search" in registry.names()
    assert "supplier.compare" not in registry.names()


@pytest.mark.anyio
async def test_model_gateway_none_fail_closed():
    gateway = AdapterModelGateway(NoneAdapter())
    with pytest.raises(Exception) as exc:
        await gateway.generate_answer(session_id="s", message="hi", context={}, trace_id="t")
    assert getattr(exc.value, "code").value == "CAPABILITY_DISABLED"
