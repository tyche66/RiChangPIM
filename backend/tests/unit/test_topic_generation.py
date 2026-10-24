"""Track B：独立选题真实生成链路测试。

覆盖验收项：
* 成功：Skill 提示词 -> AI -> schema 校验 -> 落库 ContentTopicItem，run 推到 done；
* AI 不可用（NoneAdapter / 适配器抛错）：run -> failed 且 error_msg 落库，接口 503；
* AI 返回非法 JSON：run -> failed，接口 422；
* AI 返回不符合 output_schema 的结构：run -> failed，接口 422；
* 全部选题未通过合规校验：run -> failed，接口 422；
* 采纳选题会预建内容批次（工坊跳转闭环）；
* 生成时带上 topic_item_id，选题条目推进到 used 并回写批次。

用内存假适配器 + 假 Session 执行，不连数据库。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.adapters.none import NoneAdapter
from app.api.v1 import content_skills
from app.models.content import ContentBatch
from app.models.content_skill import ContentSkill, ContentTopicItem, ContentTopicRun
from app.schemas.content import ContentGenerateRequest
from app.services.content_service import ContentGenerationError, ContentService
from app.services.topic_service import (
    TOPIC_OUTPUT_SCHEMA,
    TopicGenerationError,
    TopicService,
    build_topic_prompt,
    check_topic_compliance,
    extract_json,
    validate_against_schema,
    validate_topic_output_schema,
)

# ---------------------------------------------------------------------------
# 假适配器 / 假 Session
# ---------------------------------------------------------------------------


class FakeAdapter:
    def __init__(self, answer: str = "", raise_error: Exception | None = None):
        self.answer = answer
        self.raise_error = raise_error
        self.calls: list[dict] = []

    async def chat(self, *, session_id, message, history, stream=False):
        self.calls.append({"session_id": session_id, "message": message})
        if self.raise_error is not None:
            raise self.raise_error
        return {"answer": self.answer}


class _FakeResult:
    """同时支持 scalars() 与 scalar_one_or_none() 两种调用。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return iter(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """只实现选题服务用到的几个方法。"""

    def __init__(self, products=None):
        self.products = products or []
        self.added: list = []
        self.commits = 0
        self.refreshed: list = []

    async def execute(self, statement):
        return _FakeResult(self.products)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


class SkillSession(FakeSession):
    """模拟 _get_enabled_skill 查到的启用 Skill。"""

    def __init__(self, skill=None, products=None):
        super().__init__(products=products)
        self.skill = skill

    async def execute(self, statement):
        if self.skill is not None:
            return _FakeResult([self.skill])
        return _FakeResult([])


class ContentSession(FakeSession):
    """Sequential fake responses for ContentService topic-batch reuse tests."""

    def __init__(self, *responses):
        super().__init__()
        self.responses = list(responses)

    async def execute(self, statement):
        if not self.responses:
            raise AssertionError("unexpected database query")
        return self.responses.pop(0)


def _skill(**overrides):
    data = {
        "id": "skill-1",
        "code": "topic-basic",
        "name": "基础选题",
        "skill_type": "topic",
        "prompt_version": "v1",
        "output_schema": TOPIC_OUTPUT_SCHEMA,
        "enabled": True,
    }
    data.update(overrides)
    return ContentSkill(**data)


def _run(**overrides):
    data = {
        "id": "11111111-1111-1111-1111-111111111111",
        "skill_id": "22222222-2222-2222-2222-222222222222",
        "skill_code": "topic-basic",
        "topic": "现代办公空间的弧形会议桌怎么选",
        "requested_count": 3,
        "status": "running",
        "product_ids": [],
        "prompt_version": "v1",
    }
    data.update(overrides)
    return ContentTopicRun(**data)


def _answer(items: list[dict]) -> str:
    return json.dumps({"items": items}, ensure_ascii=False)


def _item_payload(title="弧形会议桌的三种搭配法", **overrides):
    payload = {
        "title": title,
        "angle": "从空间动线讲弧形桌如何撑起小会议室",
        "audience": "行政采购与空间设计师",
        "reason": "弧形桌面是本次主题的差异点",
        "suggested_platform": "xhs",
        "related_product_ids": [],
    }
    payload.update(overrides)
    return payload


class _FakeHeaders(dict):
    def get(self, key, default=None):
        return dict.get(self, key.lower(), default)


def _fake_request(user_id=None, role_code="admin"):
    return SimpleNamespace(
        state=SimpleNamespace(user_id=user_id, role_code=role_code),
        headers=_FakeHeaders(),
        url=SimpleNamespace(path="/api/v1/content/topics/runs"),
        method="POST",
        client=None,
    )


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


def test_prompt_uses_skill_template_and_injects_facts():
    skill = _skill(prompt_template="主题={topic} 平台={platform} 计数={requested_count}")
    prompt = build_topic_prompt(
        skill,
        topic="弧形会议桌",
        platform="xhs",
        tone=None,
        products=[{"id": "p1", "product_name": "弧形会议桌", "product_no": "EN74-2.320162"}],
        requested_count=2,
    )
    assert "主题=弧形会议桌" in prompt
    assert "平台=xhs" in prompt
    assert "计数=2" in prompt
    assert "弧形会议桌" in prompt


def test_prompt_falls_back_when_template_missing():
    skill = _skill(prompt_template=None)
    prompt = build_topic_prompt(
        skill, topic="弧形会议桌", platform=None, tone=None, products=[], requested_count=1
    )
    assert "选题清单" in prompt


def test_prompt_tolerates_broken_template():
    skill = _skill(prompt_template="坏模板 { 未闭合")
    prompt = build_topic_prompt(
        skill, topic="t", platform=None, tone=None, products=[], requested_count=1
    )
    assert "选题清单" in prompt


def test_extract_json_handles_code_fence():
    assert extract_json('```json\n{"items": []}\n```') == {"items": []}


def test_extract_json_rejects_garbage():
    with pytest.raises((json.JSONDecodeError, ValueError)):
        extract_json("这不是 JSON")


def test_validate_against_schema_reports_missing_required():
    errors = validate_against_schema({"items": [{"title": "t"}]}, TOPIC_OUTPUT_SCHEMA)
    assert errors
    assert any("angle" in e or "audience" in e for e in errors)


def test_validate_against_schema_accepts_valid_payload():
    assert validate_against_schema({"items": [_item_payload()]}, TOPIC_OUTPUT_SCHEMA) == []


def test_topic_schema_must_expose_persisted_fields():
    schema = {
        "type": "object",
        "required": ["items"],
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["headline", "angle", "audience"],
                    "properties": {
                        "headline": {"type": "string"},
                        "angle": {"type": "string"},
                        "audience": {"type": "string"},
                    },
                },
            }
        },
    }
    errors = validate_topic_output_schema(schema)
    assert any("title" in error for error in errors)


def test_topic_prompt_injects_custom_output_schema():
    custom_schema = {
        "type": "object",
        "required": ["items"],
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "angle", "audience"],
                    "properties": {
                        "title": {"type": "string"},
                        "angle": {"type": "string"},
                        "audience": {"type": "string"},
                    },
                },
            }
        },
    }
    prompt = build_topic_prompt(
        _skill(output_schema=custom_schema),
        topic="t",
        platform=None,
        tone=None,
        products=[],
        requested_count=1,
    )
    assert '"headline"' not in prompt
    assert '"title"' in prompt


def test_topic_prompt_appends_schema_when_custom_template_omits_placeholder():
    custom_schema = {
        "type": "object",
        "required": ["items"],
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "angle", "audience"],
                    "properties": {
                        "title": {"type": "string"},
                        "angle": {"type": "string"},
                        "audience": {"type": "string"},
                    },
                },
            }
        },
    }
    prompt = build_topic_prompt(
        _skill(prompt_template="仅生成选题：{topic}", output_schema=custom_schema),
        topic="t",
        platform=None,
        tone=None,
        products=[],
        requested_count=1,
    )
    assert '"required": [' in prompt
    assert '"title"' in prompt


def test_topic_platform_resolution_never_returns_null():
    item = ContentTopicItem(
        id="33333333-3333-3333-3333-333333333333",
        run_id="11111111-1111-1111-1111-111111111111",
        title="标题",
        source_skill_code="topic-basic",
    )
    run = ContentTopicRun(
        id="11111111-1111-1111-1111-111111111111",
        skill_id="22222222-2222-2222-2222-222222222222",
        skill_code="topic-basic",
        topic="主题",
        requested_count=1,
    )
    skill = _skill(supported_platforms=["douyin"])

    assert content_skills._resolve_topic_platform(item, run, skill) == "douyin"
    item.suggested_platform = "moments"
    assert content_skills._resolve_topic_platform(item, run, skill) == "moments"
    item.suggested_platform = None
    skill.supported_platforms = []
    assert content_skills._resolve_topic_platform(item, run, skill) == "xhs"


@pytest.mark.asyncio
async def test_adopt_topic_item_creates_batch_with_supported_platform():
    item = ContentTopicItem(
        id="33333333-3333-3333-3333-333333333333",
        run_id="11111111-1111-1111-1111-111111111111",
        title="办公桌选题",
        angle="空间利用",
        audience="行政采购",
        source_skill_code="topic-basic",
        related_product_ids=[],
        status="draft",
    )
    run = ContentTopicRun(
        id="11111111-1111-1111-1111-111111111111",
        skill_id="22222222-2222-2222-2222-222222222222",
        skill_code="topic-basic",
        topic="办公空间",
        platform=None,
        requested_count=1,
    )
    skill = _skill(supported_platforms=["douyin"])
    db = ContentSession(
        _FakeResult([item]),
        _FakeResult([run]),
        _FakeResult([skill]),
    )

    result = await content_skills.adopt_topic_item(
        _fake_request(), item.id, db
    )

    batch = next(obj for obj in db.added if isinstance(obj, ContentBatch))
    assert batch.platform == "douyin"
    assert item.content_batch_id == batch.id
    assert result["data"]["content_batch_id"] == str(batch.id)


def test_validate_against_schema_flags_extra_fields():
    payload = _item_payload(unexpected="x")
    errors = validate_against_schema({"items": [payload]}, TOPIC_OUTPUT_SCHEMA)
    assert any("unexpected" in e for e in errors)


def test_compliance_detects_ad_law_words_and_promises():
    warnings = check_topic_compliance("全网最低价的弧形会议桌", None, None)
    assert any("极限词" in w for w in warnings)
    warnings = check_topic_compliance("保证 30 天交付", None, None)
    assert any("承诺性" in w for w in warnings)


def test_compliance_clean_text_passes():
    assert check_topic_compliance("弧形会议桌的三种搭配法", "空间动线", "行政采购") == []


# ---------------------------------------------------------------------------
# 生成链路
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_success_creates_items_and_done_run():
    adapter = FakeAdapter(_answer([_item_payload(), _item_payload(title="第二条")]))
    db = FakeSession()
    run = _run(requested_count=2)
    skill = _skill()

    items = await TopicService(adapter, db, model="gpt-4o-mini").generate(
        run, skill, {"sub": None}
    )

    assert len(items) == 2
    assert all(isinstance(i, ContentTopicItem) for i in items)
    assert [i.title for i in items] == ["弧形会议桌的三种搭配法", "第二条"]
    assert run.status == "done"
    assert run.error_msg is None
    assert run.latency_ms is not None
    assert run.model_name == "gpt-4o-mini"
    assert run.prompt_version == "v1"
    assert len(db.added) == 2
    # 落库条目携带来源 Skill 编码，便于回溯"选题来自哪个 Skill"
    assert all(i.source_skill_code == "topic-basic" for i in items)


@pytest.mark.asyncio
async def test_generate_truncates_to_requested_count():
    adapter = FakeAdapter(
        _answer([_item_payload(title=f"选题{i}") for i in range(5)])
    )
    run = _run(requested_count=2)
    items = await TopicService(adapter, FakeSession(), model="m").generate(
        run, _skill(), {"sub": None}
    )
    assert len(items) == 2


@pytest.mark.asyncio
async def test_generate_ai_unavailable_marks_run_failed():
    adapter = FakeAdapter(raise_error=RuntimeError("connection refused"))
    run = _run()
    with pytest.raises(TopicGenerationError) as exc:
        await TopicService(adapter, FakeSession(), model="m").generate(
            run, _skill(), {"sub": None}
        )
    assert exc.value.code == 50302
    assert run.status == "failed"
    assert "RuntimeError" in (run.error_msg or "")
    assert "connection refused" not in (run.error_msg or "")


@pytest.mark.asyncio
async def test_generate_invalid_json_marks_run_failed():
    adapter = FakeAdapter("这不是 JSON")
    run = _run()
    with pytest.raises(TopicGenerationError) as exc:
        await TopicService(adapter, FakeSession(), model="m").generate(
            run, _skill(), {"sub": None}
        )
    assert exc.value.code == 40001
    assert run.status == "failed"
    assert "格式" in (run.error_msg or "")


@pytest.mark.asyncio
async def test_generate_schema_violation_marks_run_failed():
    adapter = FakeAdapter(_answer([{"title": "只有标题"}]))
    run = _run()
    with pytest.raises(TopicGenerationError) as exc:
        await TopicService(adapter, FakeSession(), model="m").generate(
            run, _skill(), {"sub": None}
        )
    assert exc.value.code == 40001
    assert run.status == "failed"
    assert "Schema" in (run.error_msg or "")


@pytest.mark.asyncio
async def test_generate_all_items_dropped_by_compliance_marks_run_failed():
    adapter = FakeAdapter(_answer([_item_payload(title="全网最低弧形会议桌")]))
    run = _run()
    with pytest.raises(TopicGenerationError) as exc:
        await TopicService(adapter, FakeSession(), model="m").generate(
            run, _skill(), {"sub": None}
        )
    assert exc.value.code == 40001
    assert run.status == "failed"
    assert "合规" in (run.error_msg or "")


@pytest.mark.asyncio
async def test_generate_keeps_compliant_items_and_drops_violations():
    adapter = FakeAdapter(
        _answer([
            _item_payload(title="合规选题"),
            _item_payload(title="全网最低价的选题"),
        ])
    )
    run = _run(requested_count=2)
    items = await TopicService(adapter, FakeSession(), model="m").generate(
        run, _skill(), {"sub": None}
    )
    assert [i.title for i in items] == ["合规选题"]
    assert run.status == "done"


@pytest.mark.asyncio
async def test_generate_empty_items_marks_run_failed():
    adapter = FakeAdapter(_answer([]))
    run = _run()
    with pytest.raises(TopicGenerationError):
        await TopicService(adapter, FakeSession(), model="m").generate(
            run, _skill(), {"sub": None}
        )
    assert run.status == "failed"


@pytest.mark.asyncio
async def test_related_product_ids_filtered_to_known_products():
    known = "11111111-1111-1111-1111-111111111111"
    adapter = FakeAdapter(_answer([_item_payload(related_product_ids=[known, "p-unknown"])]))
    run = _run(product_ids=[known])
    db = FakeSession(
        products=[
            SimpleNamespace(
                id=known,
                product_name="弧形会议桌",
                product_no="EN74-2.320162",
                specification="3200*1620*760",
                series="EN74",
            )
        ]
    )
    items = await TopicService(adapter, db, model="m").generate(
        run, _skill(), {"sub": None}
    )
    assert items[0].related_product_ids == [known]


@pytest.mark.asyncio
async def test_content_generation_reuses_adopted_topic_batch_and_marks_used():
    batch = ContentBatch(
        id="44444444-4444-4444-4444-444444444444",
        title="预建批次",
        topic="选题上下文",
        platform="xhs",
        product_ids=[],
        requested_count=1,
        status="pending",
    )
    topic_item = ContentTopicItem(
        id="33333333-3333-3333-3333-333333333333",
        run_id="11111111-1111-1111-1111-111111111111",
        title="标题",
        angle="角度",
        audience="人群",
        source_skill_code="topic-basic",
        status="adopted",
        content_batch_id=batch.id,
    )
    answer = json.dumps(
        {
            "items": [
                {
                    "title": "内容标题",
                    "body": (
                        "这是一段长度足够超过三十个字符的内容正文，"
                        "用于验证预建批次会被原地复用。"
                    ),
                    "hashtags": [],
                }
            ]
        },
        ensure_ascii=False,
    )
    adapter = FakeAdapter(answer)
    db = ContentSession(
        _FakeResult([topic_item]),
        _FakeResult([batch]),
        _FakeResult([]),
    )
    body = ContentGenerateRequest(
        title="工坊标题",
        topic="工坊主题",
        platform="douyin",
        requested_count=1,
        topic_item_id=topic_item.id,
    )

    result = await ContentService(adapter, db, model="m").generate(
        body,
        {"sub": None, "role_code": "operator"},
    )

    assert result["batch"] is batch
    assert batch.id == topic_item.content_batch_id
    assert batch.platform == "douyin"
    assert topic_item.status == "used"
    assert not any(isinstance(obj, ContentBatch) for obj in db.added)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "used", "rejected"])
async def test_content_generation_rejects_non_adopted_topic_item(status):
    topic_item = ContentTopicItem(
        id="33333333-3333-3333-3333-333333333333",
        run_id="11111111-1111-1111-1111-111111111111",
        title="标题",
        source_skill_code="topic-basic",
        status=status,
    )
    body = ContentGenerateRequest(
        title="工坊标题",
        topic="工坊主题",
        platform="xhs",
        topic_item_id=topic_item.id,
    )
    with pytest.raises(ContentGenerationError) as exc:
        await ContentService(
            FakeAdapter(),
            ContentSession(_FakeResult([topic_item])),
            model="m",
        ).generate(
            body,
            {"sub": None, "role_code": "operator"},
        )
    assert exc.value.code == 40401


# ---------------------------------------------------------------------------
# API 层
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_topic_run_returns_generated_items():
    """端点必须返回真实生成的选题条目，而不是空壳 run。"""

    adapter = FakeAdapter(_answer([_item_payload()]))
    request = _fake_request()
    topic_skill = _skill(code="yuc-topic", source_dna="yuc")
    payload = content_skills.TopicRunCreateRequest(
        skill_code="yuc-topic",
        topic="弧形会议桌怎么选",
        requested_count=1,
    )

    result = await content_skills.create_topic_run(
        request=request,
        payload=payload,
        adapter=adapter,
        db=SkillSession(skill=topic_skill),
    )
    data = result["data"]
    assert data["status"] == "done"
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "弧形会议桌的三种搭配法"


@pytest.mark.asyncio
async def test_create_topic_run_without_adapter_is_503():
    from fastapi import HTTPException

    request = _fake_request()
    payload = content_skills.TopicRunCreateRequest(
        skill_code="topic-basic", topic="t", requested_count=1
    )
    with pytest.raises(HTTPException) as exc:
        await content_skills.create_topic_run(
            request=request,
            payload=payload,
            adapter=NoneAdapter(),
            db=SkillSession(skill=_skill()),
        )
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == 50302


@pytest.mark.asyncio
async def test_create_topic_run_failure_returns_422_and_keeps_failed_run():
    from fastapi import HTTPException

    adapter = FakeAdapter("坏输出")
    request = _fake_request()
    payload = content_skills.TopicRunCreateRequest(
        skill_code="yuc-topic", topic="t", requested_count=1
    )
    session = SkillSession(skill=_skill(code="yuc-topic", source_dna="yuc"))

    with pytest.raises(HTTPException) as exc:
        await content_skills.create_topic_run(
            request=request,
            payload=payload,
            adapter=adapter,
            db=session,
        )
    assert exc.value.status_code == 422
    # 失败原因必须落库（commit 至少被调用一次），run 状态为 failed
    assert session.commits >= 1
    failed_runs = [obj for obj in session.added if isinstance(obj, ContentTopicRun)]
    assert failed_runs and failed_runs[0].status == "failed"
    assert failed_runs[0].error_msg

def test_topic_context_includes_title_angle_audience():
    item = ContentTopicItem(
        id="item-1",
        run_id="run-1",
        title="弧形会议桌的三种搭配法",
        angle="空间动线",
        audience="行政采购",
        reason="差异点",
        source_skill_code="topic-basic",
    )
    context = content_skills._topic_context(item)
    assert "弧形会议桌的三种搭配法" in context
    assert "空间动线" in context
    assert "行政采购" in context


def test_topic_item_dict_exposes_batch_link():
    item = ContentTopicItem(
        id="item-1",
        run_id="run-1",
        title="t",
        source_skill_code="topic-basic",
    )
    data = content_skills._topic_item_to_dict(item)
    assert data["content_batch_id"] is None
