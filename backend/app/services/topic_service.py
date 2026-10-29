"""独立选题生成（Track B）。

``POST /content/topics/runs`` 以前只建一条 ``status=running`` 的记录就返回，
前端却显示"选题已生成"——实际没有任何选题条目。本服务把它补成真链路：

1. 用所选 Skill 的 ``prompt_template``（缺省时退回内置模板）拼提示词；
2. 调用 AI 适配器拿 JSON 输出；
3. 按 Skill 的 ``output_schema``（缺省时退回内置 schema）校验；
4. 逐条做合规检查，不通过的条目丢弃并计数；
5. 落库 ``ContentTopicItem``，并把 run 从 ``running`` 推到 ``done`` / ``failed``，
   失败原因写入 ``error_msg``。

采用选题 Skill 的 ``prompt_version`` 作为版本标记，与内容生成保持一致。
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from app.adapters.base import AIServiceAdapter
from app.models.content_skill import ContentSkill, ContentTopicItem, ContentTopicRun
from app.models.product import Product
from app.services.content_dna import PILLAR_CODES
from app.services.content_facts import PRODUCT_FACT_OPTIONS, product_fact_payload

logger = logging.getLogger(__name__)

# 与服务层提示词同一套占位符：{topic}/{platform}/{tone}/{product_facts}/
# {output_schema}/{requested_count}
DEFAULT_TOPIC_PROMPT = """你是办公家具品牌的选题助手：挑出具体、可执行、值得做的内容角度，\
生成可执行的选题清单。
不要写成行业报告、产品说明或参数罗列。
选题判断标准：
1. 每条选题只聚焦一个具体办公场景问题、选择判断、常见误解或细节发现。
2. title 要像一个内容标题：带场景、人群或反差，让人想点进来；不要堆型号和参数。
3. angle 写清这条内容具体讲什么、给读者一个什么可执行的判断；不要写抽象概念或口号。
4. audience 写具体人群和处境；reason 说明为什么现在值得做；suggested_platform 只从给定平台里选。
5. related_product_ids 只能引用上面给出的产品 ID；标题不超过 30 字。
事实规则只在后台执行，绝不能变成选题的口吻：
1. 只使用给出的产品事实；规格、型号和数值必须原样准确，不可推导出未提供的性能承诺。
2. 缺少某项事实时，把该角度改成不依赖该事实的问题或行动建议；不要在\
title/angle/audience/reason 里写“待核验”“资料不足”“无法确认”等字样，\
核验缺口只写 verification_gaps。
3. 不得编造产品不存在的能力，不得编造价格、折扣、库存、交期、材质、认证、排名、\
客户评价、案例、功效或售后；不得使用绝对化、夸大化承诺。
4. 严格只输出符合 output_schema 的 JSON，不要输出 Markdown、代码围栏或解释。

主题：{topic}
平台：{platform}
风格：{tone}
数量：{requested_count}

可参考的产品事实（仅限以下信息，禁止编造）：
{product_facts}

输出格式：
{output_schema}
"""

TOPIC_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["items"],
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "required": ["title", "angle", "audience"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "maxLength": 60},
                    "angle": {"type": "string", "maxLength": 300},
                    "audience": {"type": "string", "maxLength": 120},
                    "reason": {"type": "string", "maxLength": 300},
                    "suggested_platform": {"type": "string", "maxLength": 32},
                    "related_product_ids": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 64},
                    },
                    "pillar_code": {"type": "string", "enum": list(PILLAR_CODES)},
                    "verification_gaps": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 240},
                    },
                },
            },
        }
    },
}

_TOPIC_REQUIRED_ITEM_FIELDS = ("title", "angle", "audience")

PILLAR_TARGETS = {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2}


def allocate_pillar_codes(
    existing_counts: dict[str, int] | None,
    requested_count: int,
    *,
    existing_window: list[str] | None = None,
) -> list[str]:
    """Allocate a small batch by cumulative deficit toward the 20-item target.

    The repeated max-deficit choice makes small batches fill the current gap
    instead of restarting a fixed A/B/C/D/E list every run.  Ties are stable
    in target order, so a fresh window starts at A and remains deterministic.
    """
    counts = {code: max(0, int((existing_counts or {}).get(code, 0))) for code in PILLAR_CODES}
    window = list(existing_window or [])[-20:]
    result: list[str] = []
    for _ in range(max(0, requested_count)):
        # A new generated topic enters the rolling window before its pillar is
        # selected, so account for the item that the new row will evict first.
        if existing_window is not None and len(window) >= 20:
            evicted = window.pop(0)
            if evicted in counts:
                counts[evicted] = max(0, counts[evicted] - 1)
        code = max(
            PILLAR_CODES,
            key=lambda item: (
                (PILLAR_TARGETS[item] - counts[item]) / PILLAR_TARGETS[item],
                -counts[item],
                -PILLAR_CODES.index(item),
            ),
        )
        result.append(code)
        counts[code] += 1
        if existing_window is not None:
            window.append(code)
    return result


def validate_topic_output_schema(schema: Any) -> list[str]:
    """Validate the persisted-field contract for a topic Skill.

    Topic items are persisted into fixed columns rather than an opaque JSON
    payload.  A custom schema therefore has to describe the fields that the
    service can actually store; accepting an arbitrary schema would let a
    schema-valid response turn into an empty database row.
    """
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["Schema 必须是 object"]

    if schema.get("type") != "object":
        errors.append("$ 必须声明 type=object")
    if schema.get("additionalProperties") is not False:
        errors.append("$ 必须禁止未声明字段")
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(field, str) for field in required):
        errors.append("$.required 必须是数组")
    elif "items" not in required:
        errors.append("$ 必须要求 items")

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return errors + ["$.properties 必须是 object"]
    if set(properties) != {"items"}:
        errors.append("$ 仅允许 items 字段")

    items_schema = properties.get("items")
    if not isinstance(items_schema, dict) or items_schema.get("type") != "array":
        return errors + ["$.items 必须声明 type=array"]

    item_schema = items_schema.get("items")
    if not isinstance(item_schema, dict) or item_schema.get("type") != "object":
        return errors + ["$.items.items 必须声明 type=object"]
    if item_schema.get("additionalProperties") is not False:
        errors.append("$.items.items 必须禁止未声明字段")

    item_properties = item_schema.get("properties")
    if not isinstance(item_properties, dict):
        return errors + ["$.items.items.properties 必须是 object"]
    persisted_fields = {
        "title", "angle", "audience", "reason", "suggested_platform", "related_product_ids",
        "pillar_code", "verification_gaps",
    }
    unsupported_fields = set(item_properties) - persisted_fields
    if unsupported_fields:
        errors.append(f"$.items.items.properties 包含未持久化字段: {sorted(unsupported_fields)}")

    item_required = item_schema.get("required", [])
    if not isinstance(item_required, list) or any(
        not isinstance(field, str) for field in item_required
    ):
        errors.append("$.items.items.required 必须是字符串数组")
        item_required = []
    required = set(item_required)
    for field in _TOPIC_REQUIRED_ITEM_FIELDS:
        if field not in required:
            errors.append(f"$.items.items 必须要求 {field}")
        field_schema = item_properties.get(field)
        if not isinstance(field_schema, dict) or field_schema.get("type") != "string":
            errors.append(f"$.items.items.properties.{field} 必须声明 type=string")
    for field in ("reason", "suggested_platform"):
        field_schema = item_properties.get(field)
        if field_schema is not None and (
            not isinstance(field_schema, dict) or field_schema.get("type") != "string"
        ):
            errors.append(f"$.items.items.properties.{field} 必须声明 type=string")
    related_schema = item_properties.get("related_product_ids")
    if related_schema is not None and (
        not isinstance(related_schema, dict) or related_schema.get("type") != "array"
    ):
        errors.append("$.items.items.properties.related_product_ids 必须声明 type=array")

    pillar_schema = item_properties.get("pillar_code")
    if pillar_schema is not None and (
        not isinstance(pillar_schema, dict) or pillar_schema.get("type") != "string"
    ):
        errors.append("$.items.items.properties.pillar_code 必须声明 type=string")
    gaps_schema = item_properties.get("verification_gaps")
    if gaps_schema is not None and (
        not isinstance(gaps_schema, dict) or gaps_schema.get("type") != "array"
    ):
        errors.append("$.items.items.properties.verification_gaps 必须声明 type=array")

    return errors

_COMMIT_PATTERN = re.compile(r"\d+\s*元|￥\d+|最低|保证\s*\d+\s*天")
_AD_LAW_WORDS = [
    "国家级", "最高级", "最佳", "最低", "最便宜", "最新", "最先进",
    "全网最低", "全网最高", "全球最低", "全球最高",
    "100%", "绝对", "永久", "万能", "特效", "高效",
]


class TopicGenerationError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


# ---------------------------------------------------------------------------
# 提示词渲染
# ---------------------------------------------------------------------------


class _SafeDict(dict):
    """未知占位符保持原样，避免自定义模板因为少一个键就整体崩掉。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def build_topic_prompt(
    skill: ContentSkill,
    *,
    topic: str,
    platform: str | None,
    tone: str | None,
    products: list[dict[str, Any]],
    requested_count: int,
    pillar_quota: str | None = None,
) -> str:
    template = (skill.prompt_template or "").strip() or DEFAULT_TOPIC_PROMPT
    output_schema = skill.output_schema or TOPIC_OUTPUT_SCHEMA
    product_facts = json.dumps(
        [dict(p) for p in products],
        ensure_ascii=False,
        indent=2,
    )
    values = {
        "topic": topic,
        "platform": platform or "不限",
        "tone": tone or "不限",
        "product_facts": product_facts,
        "output_schema": json.dumps(output_schema, ensure_ascii=False, indent=2),
        "requested_count": str(requested_count),
        "count": str(requested_count),
        "pillar_quota": pillar_quota or "按当前滚动窗口缺口分配",
        "skill_code": skill.code,
        "skill_name": skill.name,
    }
    try:
        prompt = template.format_map(_SafeDict(values))
    except (KeyError, IndexError, ValueError):
        # 模板本身不合法（如裸 { } 花括号）时退回内置提示词，绝不静默失败
        logger.warning("topic prompt render failed, fallback to default", exc_info=True)
        prompt = DEFAULT_TOPIC_PROMPT.format_map(_SafeDict(values))
    if values["output_schema"] not in prompt:
        prompt += "\n\n输出必须符合以下 JSON Schema：\n" + values["output_schema"]
    return prompt


# ---------------------------------------------------------------------------
# JSON 抽取与 schema 校验（JSON-Schema 的一个小子集）
# ---------------------------------------------------------------------------


def extract_json(text: str) -> Any:
    text = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    return json.loads(text)


_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def validate_against_schema(data: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """极简 JSON-Schema 校验，返回错误列表（空列表表示通过）。

    只实现项目用到的子集：type / required / properties / additionalProperties /
    items / maxLength / minLength / maxItems / minItems / enum。
    """
    errors: list[str] = []

    expected = schema.get("type")
    if expected is not None:
        python_type = _TYPE_MAP.get(expected)
        if python_type is not None and not isinstance(data, python_type):
            return [f"{path}: 期望 {expected}，实际 {type(data).__name__}"]
        if expected == "integer" and isinstance(data, bool):
            return [f"{path}: 期望 integer，实际 boolean"]

    if isinstance(data, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"{path}: 缺少必填字段 {key}")
        if schema.get("additionalProperties") is False:
            for key in data:
                if key not in properties:
                    errors.append(f"{path}: 不允许的字段 {key}")
        for key, value in data.items():
            if key in properties:
                errors.extend(validate_against_schema(value, properties[key], f"{path}.{key}"))

    if isinstance(data, list):
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(data):
                errors.extend(
                    validate_against_schema(item, item_schema, f"{path}[{index}]")
                )
        if "maxItems" in schema and len(data) > schema["maxItems"]:
            errors.append(f"{path}: 最多 {schema['maxItems']} 项，实际 {len(data)}")
        if "minItems" in schema and len(data) < schema["minItems"]:
            errors.append(f"{path}: 至少 {schema['minItems']} 项，实际 {len(data)}")

    if isinstance(data, str):
        if "minLength" in schema and len(data) < schema["minLength"]:
            errors.append(f"{path}: 最短 {schema['minLength']} 字，实际 {len(data)}")
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            errors.append(f"{path}: 最长 {schema['maxLength']} 字，实际 {len(data)}")
        if "minLength" in schema and len(data) < schema["minLength"]:
            errors.append(f"{path}: 最短 {schema['minLength']} 字，实际 {len(data)}")

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: 取值必须是 {schema['enum']}")

    return errors


def check_topic_compliance(*texts: str | None) -> list[str]:
    """选题合规检查：承诺性措辞 + 广告法极限词。"""
    warnings: list[str] = []
    for text in texts:
        if not text:
            continue
        if _COMMIT_PATTERN.search(text):
            warnings.append("含承诺性措辞（价格/保证天数等）")
        for word in _AD_LAW_WORDS:
            if word in text:
                warnings.append(f"含广告法极限词: {word}")
    return list(dict.fromkeys(warnings))


# ---------------------------------------------------------------------------
# 生成服务
# ---------------------------------------------------------------------------


class TopicService:
    """选题生成服务：提示词 -> AI -> schema 校验 -> 合规 -> 落库。"""

    def __init__(
        self,
        adapter: AIServiceAdapter | None,
        db: Any,
        *,
        model: str,
    ):
        self.adapter = adapter
        self.db = db
        self.model = model

    async def _load_recent_pillar_counts(self) -> dict[str, int]:
        """Read only the latest 20 topic items; no product/embedding lookup."""
        result = await self.db.execute(
            select(ContentTopicItem.pillar_code)
            .where(
                ContentTopicItem.is_deleted.is_(False),
                ContentTopicItem.pillar_code.is_not(None),
            )
            .order_by(ContentTopicItem.create_time.desc())
            .limit(20)
        )
        values = result.scalars()
        values = values.all() if hasattr(values, "all") else list(values)
        counts = {code: 0 for code in PILLAR_CODES}
        for value in values:
            if value in counts:
                counts[value] += 1
        return counts

    async def _load_recent_pillar_window(self) -> list[str]:
        """Return the latest rolling window ordered from oldest to newest."""
        result = await self.db.execute(
            select(ContentTopicItem.pillar_code)
            .where(
                ContentTopicItem.is_deleted.is_(False),
                ContentTopicItem.pillar_code.is_not(None),
            )
            .order_by(ContentTopicItem.create_time.desc())
            .limit(20)
        )
        values = result.scalars()
        rows = values.all() if hasattr(values, "all") else list(values)
        return [value for value in reversed(rows) if value in PILLAR_CODES]

    async def _load_products(self, product_ids: list[Any]) -> list[dict[str, Any]]:
        if not product_ids:
            return []
        stmt = (
            select(Product)
            .where(Product.id.in_(product_ids), Product.is_deleted.is_(False))
            .options(*PRODUCT_FACT_OPTIONS)
        )
        result = await self.db.execute(stmt)
        return [product_fact_payload(p) for p in result.scalars()]

    async def generate(
        self,
        run: ContentTopicRun,
        skill: ContentSkill,
        current_user: dict[str, Any],
    ) -> list[ContentTopicItem]:
        """执行生成；成功返回条目列表，失败抛 :class:`TopicGenerationError`。

        无论成功与否都会更新 run 的状态（done / failed）与错误原因。
        """
        user_id = UUID(current_user["sub"]) if current_user.get("sub") else None
        # Record the resolved model before validation/upstream work so failed
        # runs remain traceable to the model that was actually attempted.
        run.model_name = self.model
        products = await self._load_products(
            [UUID(pid) for pid in (run.product_ids or []) if pid]
        )
        known_product_ids = {p["id"] for p in products}

        schema = skill.output_schema or TOPIC_OUTPUT_SCHEMA
        schema_errors = validate_topic_output_schema(schema)
        if schema_errors:
            run.status = "failed"
            run.error_msg = f"Topic Skill Schema 无法映射到选题字段: {schema_errors[:3]}"[:500]
            run.latency_ms = 0
            await self.db.flush()
            raise TopicGenerationError(40001, "Topic Skill Schema 不符合选题字段约定")

        recent_counts = {code: 0 for code in PILLAR_CODES}
        recent_window: list[str] | None = None
        if skill.code in {"yuc-topic", "yanye-topic"}:
            try:
                recent_window = await self._load_recent_pillar_window()
                for code in recent_window:
                    recent_counts[code] += 1
            except Exception as exc:  # noqa: BLE001 - missing legacy DB shape is non-fatal
                logger.warning("pillar quota lookup fallback error_type=%s", type(exc).__name__)
                try:
                    recent_counts = await self._load_recent_pillar_counts()
                except Exception as count_exc:  # noqa: BLE001 - deterministic zero-window fallback
                    logger.warning(
                        "pillar count lookup fallback error_type=%s",
                        type(count_exc).__name__,
                    )
        pillar_targets = allocate_pillar_codes(
            recent_counts,
            run.requested_count,
            existing_window=recent_window,
        )
        start = time.perf_counter()
        prompt = build_topic_prompt(
            skill,
            topic=run.topic,
            platform=run.platform,
            tone=run.tone,
            products=products,
            requested_count=run.requested_count,
            pillar_quota=json.dumps(
                {code: PILLAR_TARGETS[code] - recent_counts[code] for code in PILLAR_CODES},
                ensure_ascii=False,
            ),
        )

        try:
            try:
                resp = await self.adapter.chat(
                    session_id=f"topic_run:{run.id}",
                    message=prompt,
                    history=[{"role": "system", "content": "你是新媒体选题助手。"}],
                    stream=False,
                    model=self.model,
                )
            except TypeError as exc:
                if "model" not in str(exc):
                    raise
                resp = await self.adapter.chat(
                    session_id=f"topic_run:{run.id}",
                    message=prompt,
                    history=[{"role": "system", "content": "你是新媒体选题助手。"}],
                    stream=False,
                )
        except Exception as exc:  # noqa: BLE001 - 统一转成 503 业务错误
            run.status = "failed"
            run.error_msg = f"AI 服务调用失败（{type(exc).__name__}）"
            run.latency_ms = int((time.perf_counter() - start) * 1000)
            await self.db.flush()
            logger.warning("topic AI call failed error_type=%s", type(exc).__name__)
            raise TopicGenerationError(50302, "AI 服务调用失败，请稍后重试") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)
        answer = resp.get("answer", "") if isinstance(resp, dict) else str(resp)

        try:
            raw = extract_json(answer)
        except (json.JSONDecodeError, ValueError) as exc:
            run.status = "failed"
            run.error_msg = f"AI 返回格式错误: {exc}"[:500]
            run.latency_ms = latency_ms
            await self.db.flush()
            raise TopicGenerationError(40001, "AI 输出不符合约定结构") from exc

        schema_errors = validate_against_schema(raw, schema)
        if schema_errors:
            run.status = "failed"
            run.error_msg = f"AI 输出不符合 Schema: {schema_errors[:3]}"[:500]
            run.latency_ms = latency_ms
            await self.db.flush()
            raise TopicGenerationError(40001, "AI 输出不符合约定结构")

        raw_items = raw.get("items") if isinstance(raw, dict) else None
        if not isinstance(raw_items, list) or not raw_items:
            run.status = "failed"
            run.error_msg = "AI 输出无有效选题"
            run.latency_ms = latency_ms
            await self.db.flush()
            raise TopicGenerationError(40001, "AI 输出无有效选题")

        items: list[ContentTopicItem] = []
        dropped_compliance = 0
        for item_index, raw_item in enumerate(raw_items[: run.requested_count]):
            if not isinstance(raw_item, dict):
                continue
            title = str(raw_item.get("title") or "").strip()
            angle = str(raw_item.get("angle") or "").strip()
            audience = str(raw_item.get("audience") or "").strip()
            reason = str(raw_item.get("reason") or "").strip() or None
            suggested_platform = (
                str(raw_item.get("suggested_platform") or "").strip() or None
            )
            if not title or not angle or not audience:
                continue

            violations = check_topic_compliance(title, angle, audience, reason)
            if violations:
                # 合规不通过的选题直接丢弃，不允许落库
                dropped_compliance += 1
                logger.info(
                    "topic dropped by compliance skill=%s title=%s violations=%s",
                    skill.code,
                    title,
                    violations,
                )
                continue

            related_ids = [
                str(pid)
                for pid in (raw_item.get("related_product_ids") or [])
                if isinstance(pid, str) and str(pid) in known_product_ids
            ]
            # The model may suggest a pillar for context, but the server-owned
            # rolling quota is authoritative for persisted traceability.
            pillar_code = pillar_targets[item_index]
            verification_gaps = raw_item.get("verification_gaps") or []
            if not isinstance(verification_gaps, list):
                verification_gaps = []
            verification_gaps = [str(gap)[:240] for gap in verification_gaps if gap][:20]
            if pillar_code == "B" and not verification_gaps:
                verification_gaps.append("需要真实项目或安装记录核验")

            item = ContentTopicItem(
                id=uuid4(),
                run_id=run.id,
                title=title,
                angle=angle,
                audience=audience,
                reason=reason,
                suggested_platform=suggested_platform,
                related_product_ids=related_ids,
                pillar_code=pillar_code,
                verification_gaps=verification_gaps,
                source_skill_code=skill.code,
                status="draft",
                create_time=datetime.now(UTC),
                update_time=datetime.now(UTC),
                created_by=user_id,
                updated_by=user_id,
            )
            self.db.add(item)
            items.append(item)

        if not items:
            run.status = "failed"
            run.error_msg = "全部选题未通过合规校验" if dropped_compliance else "AI 输出无有效选题"
            run.latency_ms = latency_ms
            await self.db.flush()
            raise TopicGenerationError(40001, run.error_msg)

        run.status = "done"
        run.latency_ms = latency_ms
        run.model_provider = "content-openai"
        run.model_name = (resp.get("model") if isinstance(resp, dict) else None) or self.model
        run.prompt_version = skill.prompt_version
        await self.db.flush()
        return items
