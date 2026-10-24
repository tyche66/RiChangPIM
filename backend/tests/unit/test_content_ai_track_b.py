"""Focused Track B contracts that do not call an external AI endpoint."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.exceptions import AIAdapterBadRequestError
from app.adapters.factory import build_adapter
from app.adapters.none import NoneAdapter
from app.adapters.openai import OpenAIAdapter, OpenAIConfig
from app.services.content_dna import (
    CONTENT_OUTPUT_SCHEMA,
    OPERATIONAL_SKILLS,
    TOPIC_OUTPUT_SCHEMA,
)
from app.services.content_skill_router import (
    SkillSelectionError,
    _auto_route,
    _parse_route_code,
    resolve_skill,
)
from app.services.topic_service import allocate_pillar_codes


def test_content_adapter_missing_key_is_fail_closed(monkeypatch):
    import app.adapters.factory as factory
    from app.core.config import settings

    monkeypatch.setattr(factory, "_cached_content_adapter", None)
    monkeypatch.setattr(settings, "CONTENT_AI_API_KEY", None, raising=False)
    monkeypatch.setattr(
        settings,
        "CONTENT_AI_CHAT_MODELS",
        "step-5-preview,sensenova-6.8-flash-lite",
        raising=False,
    )
    assert isinstance(factory.get_content_ai_adapter(), NoneAdapter)


def test_content_model_whitelist_rejects_per_request_override():
    adapter = build_adapter(
        "openai",
        api_key="test-only-key",
        chat_model="step-5-preview",
        allowed_chat_models={"step-5-preview", "sensenova-6.8-flash-lite"},
    )
    with pytest.raises(AIAdapterBadRequestError):
        adapter._resolve_chat_model("unapproved-model")  # type: ignore[attr-defined]
    assert adapter._resolve_chat_model("sensenova-6.8-flash-lite") == "sensenova-6.8-flash-lite"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_openai_chat_and_stream_apply_allowed_model_override():
    models = frozenset({"step-5-preview", "sensenova-6.8-flash-lite"})
    adapter = OpenAIAdapter(
        OpenAIConfig(
            api_key="test-only-key",
            chat_model="step-5-preview",
            allowed_chat_models=models,
        )
    )
    response = {
        "choices": [{"message": {"content": "ok", "tool_calls": None}}],
        "usage": None,
    }
    with patch.object(adapter, "_post", new=AsyncMock(return_value=response)) as post:
        await adapter.chat(
            session_id="test",
            message="safe test",
            history=[],
            model="sensenova-6.8-flash-lite",
        )
    assert post.call_args.args[1]["model"] == "sensenova-6.8-flash-lite"

    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "ok"}}]}),
        "data: [DONE]",
    ]
    response_stream = MagicMock(status_code=200)

    async def aiter_lines():
        for line in lines:
            yield line

    response_stream.aiter_lines = aiter_lines
    stream_context = MagicMock()
    stream_context.__aenter__ = AsyncMock(return_value=response_stream)
    stream_context.__aexit__ = AsyncMock(return_value=False)
    with patch.object(adapter._client, "stream", return_value=stream_context) as stream:
        async for _event in adapter.chat_stream(
            session_id="test",
            message="safe test",
            history=[],
            model="sensenova-6.8-flash-lite",
        ):
            pass
    assert stream.call_args.kwargs["json"]["model"] == "sensenova-6.8-flash-lite"
    await adapter.aclose()


def test_route_parser_only_accepts_json_skill_code():
    assert _parse_route_code('{"skill_code":"yuc-content"}') == "yuc-content"
    assert _parse_route_code("not-json") is None
    assert _parse_route_code('{"skill_code":"arbitrary"}') == "arbitrary"


class _RouteAdapter:
    def __init__(self, answer=None, error=None, delay=0):
        self.answer = answer
        self.error = error
        self.delay = delay

    async def chat(self, **kwargs):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return {"answer": self.answer}


def _skills():
    from app.models.content_skill import ContentSkill

    return [
        ContentSkill(code="yuc-content", name="禹橙", skill_type="content", source_dna="yuc"),
        ContentSkill(code="yanye-content", name="言也", skill_type="content", source_dna="yanye"),
    ]


@pytest.mark.asyncio
async def test_auto_route_valid_invalid_and_timeout_fallback():
    skills = _skills()
    valid = await _auto_route(
        skills,
        _RouteAdapter('{"skill_code":"yanye-content"}'),
        skill_type="content",
        model="step-5-preview",
    )
    assert valid is skills[1]

    invalid = await _auto_route(
        skills,
        _RouteAdapter('{"skill_code":"not-allowed"}'),
        skill_type="content",
        model="step-5-preview",
    )
    assert invalid is None

    timed_out = await _auto_route(
        skills,
        _RouteAdapter('{"skill_code":"yanye-content"}', delay=0.02),
        skill_type="content",
        model="step-5-preview",
        timeout_seconds=0.001,
    )
    assert timed_out is None


class _SkillResult:
    def __init__(self, skill):
        self.skill = skill

    def scalar_one_or_none(self):
        return self.skill


class _SkillSession:
    def __init__(self, skill):
        self.skill = skill

    async def execute(self, statement):
        return _SkillResult(self.skill)


@pytest.mark.asyncio
async def test_manual_route_rejects_legacy_and_wrong_type_skills():
    with pytest.raises(SkillSelectionError):
        await resolve_skill(
            _SkillSession(_skills()[0]),
            skill_type="topic",
            requested_code="yuc-content",
        )

    from app.models.content_skill import ContentSkill

    legacy = ContentSkill(code="topic-basic", skill_type="topic", enabled=True)
    with pytest.raises(SkillSelectionError):
        await resolve_skill(
            _SkillSession(legacy),
            skill_type="topic",
            requested_code="topic-basic",
        )


class _OperationalListResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


class _OperationalListSession:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, statement):
        return _OperationalListResult(self.rows)


@pytest.mark.asyncio
async def test_auto_resolution_falls_back_to_default_dna_on_invalid_or_timeout(monkeypatch):
    from app.core.config import settings

    skills = _skills()
    invalid = await resolve_skill(
        _OperationalListSession(skills),
        skill_type="content",
        requested_code=None,
        adapter=_RouteAdapter('{"skill_code":"not-allowed"}'),
        model="step-5-preview",
    )
    assert invalid.code == "yuc-content"

    monkeypatch.setattr(settings, "CONTENT_AI_ROUTE_TIMEOUT", 0.001)
    timed_out = await resolve_skill(
        _OperationalListSession(skills),
        skill_type="content",
        requested_code=None,
        adapter=_RouteAdapter("{}", delay=0.02),
        model="step-5-preview",
        route_context="safe test",
    )
    assert timed_out.code == "yuc-content"


def test_pillar_window_targets_and_small_batch_deficits():
    assert allocate_pillar_codes({}, 20).count("A") == 6
    assert allocate_pillar_codes({}, 20).count("B") == 5
    assert allocate_pillar_codes({}, 20).count("C") == 4
    assert allocate_pillar_codes({}, 20).count("D") == 3
    assert allocate_pillar_codes({}, 20).count("E") == 2
    assert allocate_pillar_codes({"A": 6, "B": 5, "C": 0, "D": 0, "E": 0}, 2) == ["C", "D"]
    window = list("AAAAAABBBBBCCCCDDDEE")
    rollover = allocate_pillar_codes(
        {code: window.count(code) for code in "ABCDE"},
        10,
        existing_window=window,
    )
    assert len(rollover) == 10
    assert {code: (window + rollover)[-20:].count(code) for code in "ABCDE"} == {
        "A": 6,
        "B": 5,
        "C": 4,
        "D": 3,
        "E": 2,
    }


def test_operational_schemas_and_prompts_are_local_and_fact_bounded():
    codes = {item["code"] for item in OPERATIONAL_SKILLS}
    assert codes == {"yuc-content", "yanye-content", "yuc-topic", "yanye-topic"}
    assert CONTENT_OUTPUT_SCHEMA["properties"]["items"]["items"]["properties"]["verification_gaps"]
    assert TOPIC_OUTPUT_SCHEMA["properties"]["items"]["items"]["properties"]["pillar_code"]
    all_prompts = "\n".join(item["prompt_template"] for item in OPERATIONAL_SKILLS)
    assert "CONTENT_AI_API_KEY" not in all_prompts
    assert "sk-" not in all_prompts
    assert "只使用给出的 PIM" in all_prompts


@pytest.mark.asyncio
async def test_content_skill_and_model_provenance_are_persisted_without_upstream_call():
    import json

    from app.models.content import ContentBatch, ContentItem
    from app.models.content_skill import ContentSkill
    from app.schemas.content import ContentGenerateRequest
    from app.services.content_dna import YUC_CONTENT_PROMPT
    from app.services.content_service import ContentService

    answer = json.dumps(
        {
            "items": [
                {
                    "title": "会议区选型检查",
                    "body": (
                        "先核对会议区人数、通行路径和桌面使用方式，"
                        "再对照可核验的产品资料进行选择。"
                    ),
                    "hashtags": [],
                    "mentioned_products": [],
                    "verification_gaps": [],
                    "warnings": [],
                }
            ]
        },
        ensure_ascii=False,
    )

    class Adapter:
        async def chat(self, **kwargs):
            return {"answer": answer, "model": "step-5-preview"}

    class Session:
        def __init__(self):
            self.added = []

        async def flush(self):
            return None

        def add(self, obj):
            self.added.append(obj)

    skill = ContentSkill(
        id="skill-yuc-content",
        code="yuc-content",
        name="禹橙 DNA · 内容工坊",
        skill_type="content",
        source_dna="yuc",
        prompt_template=YUC_CONTENT_PROMPT,
        output_schema=CONTENT_OUTPUT_SCHEMA,
    )
    session = Session()
    result = await ContentService(
        Adapter(), session, model="step-5-preview", skill=skill
    ).generate(
        ContentGenerateRequest(
            title="测试批次",
            topic="会议区选型",
            platform="xhs",
            requested_count=1,
            skill_code="yuc-content",
        ),
        {"sub": None},
    )

    batch = result["batch"]
    item = result["items"][0]
    assert isinstance(batch, ContentBatch)
    assert isinstance(item, ContentItem)
    assert batch.source_skill_code == item.source_skill_code == "yuc-content"
    assert batch.model_name == item.model_name == "step-5-preview"
    assert any(gap.startswith("未提供产品资料") for gap in item.verification_gaps)


def test_unverified_product_parameters_create_a_verification_gap():
    from app.services.content_service import _find_unverified_product_parameters

    products = [{"product_name": "办公桌", "specs": "1200mm x 600mm", "series": "S1"}]
    assert _find_unverified_product_parameters("桌面长1200mm，宽600mm。", products) == []
    gaps = _find_unverified_product_parameters("这款桌面长度达到1800mm。", products)
    assert gaps and "核验" in gaps[0]
