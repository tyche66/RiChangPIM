"""内容域模型选择：白名单、默认值、落库与前端契约（不调用上游）。

这些测试只使用内存假适配器 / 假 Session，不连接数据库，也不访问任何外部
模型端点。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import content, content_skills
from app.core.config import settings
from app.core.content_models import (
    ContentModelNotAllowedError,
    get_content_model_catalog,
    parse_model_allowlist,
    resolve_content_model,
)
from app.models.content import ContentBatch, ContentItem
from app.models.content_skill import ContentSkill, ContentTopicItem, ContentTopicRun
from app.schemas.content import ContentGenerateRequest
from app.services.content_dna import CONTENT_OUTPUT_SCHEMA
from app.services.content_service import ContentService
from app.services.topic_service import TOPIC_OUTPUT_SCHEMA, TopicService

DEFAULT_MODEL = "step-5-preview"
ALT_MODEL = "sensenova-6.8-flash-lite"
ALLOWED_MODELS = f"{DEFAULT_MODEL},{ALT_MODEL}"


@pytest.fixture(autouse=True)
def _content_model_settings(monkeypatch):
    monkeypatch.setattr(settings, "CONTENT_AI_CHAT_MODEL", DEFAULT_MODEL)
    monkeypatch.setattr(settings, "CONTENT_AI_CHAT_MODELS", ALLOWED_MODELS)


def _request(user_id=None, role_code="operator"):
    return SimpleNamespace(
        state=SimpleNamespace(user_id=user_id, role_code=role_code),
    )


class _ContentAnswerAdapter:
    def __init__(self, answer: str):
        self.answer = answer
        self.models: list[str | None] = []

    async def chat(self, **kwargs):
        self.models.append(kwargs.get("model"))
        return {"answer": self.answer}


class _Session:
    def __init__(self):
        self.added: list[object] = []
        self.flushes = 0
        self.commits = 0
        self.refreshed: list[object] = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


def _content_answer() -> str:
    return json.dumps(
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


def _topic_answer() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "title": "弧形会议桌怎么选",
                    "angle": "空间动线",
                    "audience": "行政采购",
                    "reason": "从使用场景切入",
                }
            ]
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 白名单与默认值
# ---------------------------------------------------------------------------


def test_allowlist_parser_preserves_order_and_deduplicates():
    assert parse_model_allowlist(" b, a ,b, , c ") == ["b", "a", "c"]


def test_catalog_and_resolution_use_default_or_explicit_allowlisted_model():
    models, default = get_content_model_catalog()
    assert models == [DEFAULT_MODEL, ALT_MODEL]
    assert default == DEFAULT_MODEL

    assert resolve_content_model(None) == DEFAULT_MODEL
    assert resolve_content_model("") == DEFAULT_MODEL
    assert resolve_content_model(ALT_MODEL) == ALT_MODEL

    with pytest.raises(ContentModelNotAllowedError):
        resolve_content_model("unapproved-model")


@pytest.mark.asyncio
async def test_model_catalog_endpoint_returns_no_secret():
    result = await content.list_content_models()
    assert result["code"] == 200
    assert result["data"] == {
        "models": [DEFAULT_MODEL, ALT_MODEL],
        "default_model": DEFAULT_MODEL,
    }
    assert "key" not in json.dumps(result["data"]).lower()


# ---------------------------------------------------------------------------
# 请求校验与路由
# ---------------------------------------------------------------------------


def test_generate_request_accepts_optional_model_name():
    body = ContentGenerateRequest(
        title="测试批次",
        topic="会议区选型",
        platform="xhs",
        model_name=ALT_MODEL,
    )
    assert body.model_name == ALT_MODEL
    assert ContentGenerateRequest(
        title="测试批次", topic="会议区选型", platform="xhs"
    ).model_name is None


@pytest.mark.asyncio
async def test_content_generate_rejects_non_allowlisted_model_with_400():
    body = ContentGenerateRequest(
        title="测试批次",
        topic="会议区选型",
        platform="xhs",
        model_name="unapproved-model",
    )
    with pytest.raises(HTTPException) as exc:
        await content.generate_content.__wrapped__(
            _request(), body, adapter=object(), db=object()
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == 40010


@pytest.mark.asyncio
async def test_content_generate_uses_selected_model_for_routing_and_service():
    captured: dict[str, object] = {}
    skill = SimpleNamespace(code="yuc-content", output_schema=CONTENT_OUTPUT_SCHEMA)

    class FakeContentService:
        def __init__(self, adapter, db, *, model, skill):
            captured["model"] = model
            captured["skill"] = skill

        async def generate(self, body, current_user):
            return {
                "batch": SimpleNamespace(
                    id=uuid4(),
                    status="done",
                    source_skill_code="yuc-content",
                    model_name=captured["model"],
                ),
                "items": [],
            }

    resolve_skill = AsyncMock(return_value=skill)
    with (
        patch(
            "app.services.content_skill_router.resolve_skill",
            new=resolve_skill,
        ),
        patch.object(content, "ContentService", FakeContentService),
    ):
        result = await content.generate_content.__wrapped__(
            _request(),
            ContentGenerateRequest(
                title="测试批次",
                topic="会议区选型",
                platform="xhs",
                model_name=ALT_MODEL,
            ),
            adapter=object(),
            db=_Session(),
        )

    assert captured["model"] == ALT_MODEL
    assert resolve_skill.await_args.kwargs["model"] == ALT_MODEL
    assert result["data"]["model_name"] == ALT_MODEL


@pytest.mark.asyncio
async def test_content_generate_without_model_uses_server_default():
    captured: dict[str, object] = {}
    skill = SimpleNamespace(code="yuc-content", output_schema=CONTENT_OUTPUT_SCHEMA)

    class FakeContentService:
        def __init__(self, adapter, db, *, model, skill):
            captured["model"] = model

        async def generate(self, body, current_user):
            return {
                "batch": SimpleNamespace(
                    id=uuid4(),
                    status="done",
                    source_skill_code="yuc-content",
                    model_name=captured["model"],
                ),
                "items": [],
            }

    resolve_skill = AsyncMock(return_value=skill)
    with (
        patch(
            "app.services.content_skill_router.resolve_skill",
            new=resolve_skill,
        ),
        patch.object(content, "ContentService", FakeContentService),
    ):
        result = await content.generate_content.__wrapped__(
            _request(),
            ContentGenerateRequest(
                title="测试批次",
                topic="会议区选型",
                platform="xhs",
            ),
            adapter=object(),
            db=_Session(),
        )

    assert captured["model"] == DEFAULT_MODEL
    assert resolve_skill.await_args.kwargs["model"] == DEFAULT_MODEL
    assert result["data"]["model_name"] == DEFAULT_MODEL


@pytest.mark.asyncio
async def test_topic_run_rejects_non_allowlisted_model_with_400():
    payload = content_skills.TopicRunCreateRequest(
        topic="会议区选型",
        model_name="unapproved-model",
    )
    with pytest.raises(HTTPException) as exc:
        await content_skills.create_topic_run.__wrapped__(
            _request(), payload, adapter=object(), db=object()
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == 40010


@pytest.mark.asyncio
async def test_topic_run_uses_selected_model_for_routing_and_service():
    captured: dict[str, object] = {}
    skill = SimpleNamespace(
        id=uuid4(),
        code="yuc-topic",
        output_schema=None,
        prompt_version="v1",
    )

    class FakeTopicService:
        def __init__(self, adapter, db, *, model):
            captured["model"] = model

        async def generate(self, run, skill, current_user):
            run.model_name = captured["model"]
            return []

    resolve_skill = AsyncMock(return_value=skill)
    with (
        patch.object(content_skills, "resolve_skill", new=resolve_skill),
        patch.object(content_skills, "TopicService", FakeTopicService),
    ):
        result = await content_skills.create_topic_run.__wrapped__(
            _request(),
            content_skills.TopicRunCreateRequest(
                topic="会议区选型",
                model_name=ALT_MODEL,
            ),
            adapter=object(),
            db=_Session(),
        )

    assert captured["model"] == ALT_MODEL
    assert resolve_skill.await_args.kwargs["model"] == ALT_MODEL
    assert result["data"]["model_name"] == ALT_MODEL


@pytest.mark.asyncio
async def test_topic_run_without_model_uses_server_default():
    captured: dict[str, object] = {}
    skill = SimpleNamespace(
        id=uuid4(),
        code="yuc-topic",
        output_schema=None,
        prompt_version="v1",
    )

    class FakeTopicService:
        def __init__(self, adapter, db, *, model):
            captured["model"] = model

        async def generate(self, run, skill, current_user):
            run.model_name = captured["model"]
            return []

    resolve_skill = AsyncMock(return_value=skill)
    with (
        patch.object(content_skills, "resolve_skill", new=resolve_skill),
        patch.object(content_skills, "TopicService", FakeTopicService),
    ):
        result = await content_skills.create_topic_run.__wrapped__(
            _request(),
            content_skills.TopicRunCreateRequest(topic="会议区选型"),
            adapter=object(),
            db=_Session(),
        )

    assert captured["model"] == DEFAULT_MODEL
    assert resolve_skill.await_args.kwargs["model"] == DEFAULT_MODEL
    assert result["data"]["model_name"] == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# 服务层：最终解析的模型用于调用并写入批次 / 选题 run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_service_calls_and_persists_selected_model():
    adapter = _ContentAnswerAdapter(_content_answer())
    session = _Session()
    skill = ContentSkill(
        id=uuid4(),
        code="yuc-content",
        name="禹橙 DNA",
        skill_type="content",
        source_dna="yuc",
        prompt_template=None,
        output_schema=CONTENT_OUTPUT_SCHEMA,
        prompt_version="v1",
    )

    result = await ContentService(
        adapter, session, model=ALT_MODEL, skill=skill
    ).generate(
        ContentGenerateRequest(
            title="测试批次",
            topic="会议区选型",
            platform="xhs",
            requested_count=1,
            model_name=ALT_MODEL,
        ),
        {"sub": None},
    )

    batch = result["batch"]
    item = result["items"][0]
    assert isinstance(batch, ContentBatch)
    assert isinstance(item, ContentItem)
    assert adapter.models == [ALT_MODEL]
    assert batch.model_name == ALT_MODEL
    assert item.model_name == ALT_MODEL


@pytest.mark.asyncio
async def test_topic_service_calls_and_persists_selected_model():
    adapter = _ContentAnswerAdapter(_topic_answer())
    session = _Session()
    skill = ContentSkill(
        id=uuid4(),
        code="topic-basic",
        name="选题基础",
        skill_type="topic",
        source_dna="yuc",
        prompt_template=None,
        output_schema=TOPIC_OUTPUT_SCHEMA,
        prompt_version="v1",
    )
    run = ContentTopicRun(
        id=uuid4(),
        skill_id=skill.id,
        skill_code=skill.code,
        topic="会议区选型",
        platform="xhs",
        tone="干货",
        product_ids=[],
        requested_count=1,
        status="running",
        prompt_version="v1",
    )

    items = await TopicService(adapter, session, model=ALT_MODEL).generate(
        run, skill, {"sub": None}
    )

    assert len(items) == 1
    assert isinstance(items[0], ContentTopicItem)
    assert adapter.models == [ALT_MODEL]
    assert run.model_name == ALT_MODEL
