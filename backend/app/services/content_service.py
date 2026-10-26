"""内容工坊业务逻辑（HLD §8.5 / §9 / §10）。"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AIServiceAdapter
from app.core.data_scope import apply_data_scope
from app.models.content import (
    ContentBatch,
    ContentItem,
    ContentMetricSnapshot,
    ContentPublication,
)
from app.models.content_skill import ContentSkill, ContentTopicItem, ContentTopicRun
from app.models.product import Product
from app.models.project import Project
from app.models.reminder import Reminder
from app.schemas.content import MetricEntry
from app.services.content_dna import CONTENT_OUTPUT_SCHEMA
from app.services.content_facts import (
    PRODUCT_FACT_OPTIONS,
    product_fact_payload,
)
from app.services.content_state import derive_display_state
from app.services.topic_service import validate_against_schema

logger = logging.getLogger(__name__)

_BEIJING_TZ = timezone(timedelta(hours=8))

_COMMIT_PATTERN = re.compile(r"\d+\s*元|￥\d+|最低|保证\s*\d+\s*天")
_PRODUCT_PARAMETER_PATTERN = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:mm|毫米|cm|厘米|m²|m2|米|平方米|㎡|kg|公斤|斤|元|万元|%|天交付|年质保|年保修)",
    re.IGNORECASE,
)

_AD_LAW_WORDS = [
    "国家级", "最高级", "最佳", "最低", "最便宜", "最新", "最先进",
    "全网最低", "全网最高", "全球最低", "全球最高",
    "100%", "绝对", "永久", "万能", "特效", "高效",
]

_R2_DAYS = [1, 3, 7]
_R1_DAYS = 2
_R1B_DAYS = 2
_CLOSED_DAYS = 14

PROMPT_VERSION = "v1"

# 生成侧人格：只负责“写成像真人分享的社媒内容”。
# 事实与合规规则由 prompt 内“只在后台执行”条款和后置守卫承担，
# 不再借 system 角色把模型按成审核员。
SYSTEM_PERSONA = (
    "你是办公家具品牌内容编辑：懂办公空间，会写具体、可信、像真人分享的社媒短文案；"
    "事实与合规规则只在后台执行，绝不写成正文口吻。"
)

OUTPUT_SCHEMA = CONTENT_OUTPUT_SCHEMA


def _build_generation_prompt(
    topic: str,
    platform: str,
    tone: str | None,
    products: list[dict],
) -> str:
    """内置回退提示词：给未配置模板的 Skill 用，写作规则与 DNA Skill 保持一致。"""
    product_facts = [dict(p) for p in products]

    prompt = f"""你是「办公家具」的品牌内容编辑：懂办公空间，也会写让用户愿意看完、收藏和互动的社媒内容。
把已提供的产品事实写成有场景、有判断、像真人分享的内容；不要写成产品说明书、白皮书、企业新闻稿或合规报告。
写作方式：
1. 每条只讲一个最值得展开的角度；标题从场景、反差、痛点或选择判断切入，避免标题党。
2. 正文前两句必须直接抓住人：写一个具体时刻、需求、反差观察或值得停下来看的细节。
3. 正文使用短段，每段一至三句；优先用画面、动词、选择理由和已确认的细节，不堆砌形容词或参数。
4. 只展开一至两个明确卖点或场景，不罗列所有资料；结尾用自然、低压力的 CTA。
5. 平台按 platform 决定体裁，语气按 tone 调整语言；平台优先于语气。
事实规则只在后台执行，绝不能变成正文的口吻：
1. 规格、型号和数值必须原样准确，不可推导出未提供的性能承诺。
2. 缺少某项事实时，删除该主张，或改写为不依赖该事实的场景、选择问题或行动建议；不要在正文解释资料不足。
3. 不得输出价格/折扣/交期/库存承诺，不得输出客户/项目/对话等隐私信息。
4. title、body 和 hashtags 中不得出现或变相出现“待核验”“资料不足”“免责声明”“仅供参考”“以实际为准”“需要明确的是”“无法确认”等审校或免责话术。
输出要求：
1. 严格只输出符合 JSON Schema 的 JSON（items 数组，每条含 title/body/hashtags），不要输出 Markdown 或解释。
2. mentioned_products 只能引用上述产品事实中的产品名称。
3. hashtags 只保留真正相关的话题标签，不适合时使用空数组。

主题：{topic}
平台：{platform}
风格：{tone or "不限"}

可引用的产品事实（仅限以下信息，禁止编造）：
{json.dumps(product_facts, ensure_ascii=False, indent=2)}

输出格式：
{json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)}"""
    return prompt


class _PromptValues(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def build_content_prompt(
    skill: ContentSkill,
    *,
    topic: str,
    platform: str,
    tone: str | None,
    products: list[dict],
    project_facts: list[dict] | None = None,
) -> str:
    """Render the selected content Skill without treating DNA as business facts."""
    product_facts = json.dumps(
        [dict(p) for p in products],
        ensure_ascii=False,
        indent=2,
    )
    schema = skill.output_schema or CONTENT_OUTPUT_SCHEMA
    values = _PromptValues(
        topic=topic,
        platform=platform,
        tone=tone or "不限",
        product_facts=product_facts,
        project_facts=json.dumps(project_facts or [], ensure_ascii=False, indent=2),
        output_schema=json.dumps(schema, ensure_ascii=False, indent=2),
        requested_count="",
        skill_code=skill.code,
        skill_name=skill.name,
    )
    template = (skill.prompt_template or "").strip()
    if not template:
        return _build_generation_prompt(topic, platform, tone, products)
    try:
        prompt = template.format_map(values)
    except (KeyError, IndexError, ValueError):
        logger.warning("content prompt render failed skill=%s", skill.code)
        prompt = _build_generation_prompt(topic, platform, tone, products)
    if values["output_schema"] not in prompt:
        prompt += "\n\n输出必须符合以下 JSON Schema：\n" + values["output_schema"]
    return prompt


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    return json.loads(text)


def _validate_schema(
    data: dict[str, Any], schema: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    if schema is not None:
        schema_errors = validate_against_schema(data, schema)
        if schema_errors:
            raise ValueError(f"AI 输出不符合 Skill Schema: {schema_errors[:3]}")
    items = data.get("items")
    if not isinstance(items, list) or len(items) == 0:
        raise ValueError("AI 输出不符合约定结构: items 为空或不是数组")
    if len(items) > 5:
        raise ValueError("AI 输出不符合约定结构: items 超过 5 条")

    validated = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "")
        body = item.get("body", "")
        hashtags = item.get("hashtags", [])
        mentioned = item.get("mentioned_products", [])
        verification_gaps = item.get("verification_gaps", [])
        item_warnings = item.get("warnings", [])

        if not isinstance(title, str) or len(title) > 60:
            title = title[:60] if isinstance(title, str) else ""
        if not isinstance(body, str) or len(body) < 30:
            continue
        if len(body) > 2000:
            body = body[:2000]
        if not isinstance(hashtags, list):
            hashtags = []
        hashtags = [h[:20] for h in hashtags if isinstance(h, str)][:10]
        if not isinstance(mentioned, list):
            mentioned = []
        if not isinstance(verification_gaps, list):
            verification_gaps = []
        if not isinstance(item_warnings, list):
            item_warnings = []

        validated.append({
            "title": title,
            "body": body,
            "hashtags": hashtags,
            "mentioned_products": mentioned,
            "verification_gaps": [str(value)[:240] for value in verification_gaps if value][:20],
            "warnings": [str(value)[:240] for value in item_warnings if value][:20],
        })

    return validated


def _check_compliance(body: str) -> list[str]:
    warnings = []
    if _COMMIT_PATTERN.search(body):
        warnings.append("含承诺性措辞（价格/保证天数等）")
    for word in _AD_LAW_WORDS:
        if word in body:
            warnings.append(f"含广告法极限词: {word}")
    return warnings


def _verify_mentioned_products(
    mentioned: list[str],
    products: list[dict],
) -> tuple[bool, list[dict], list[str]]:
    product_names = {p.get("product_name", "") for p in products}
    matched = []
    unmatched = []

    for name in mentioned:
        if name in product_names:
            matched.append(name)
        else:
            unmatched.append(name)

    verified = len(unmatched) == 0
    return verified, matched, unmatched


def _find_unverified_product_parameters(body: str, products: list[dict]) -> list[str]:
    """Flag concrete dimensions/price/warranty claims absent from selected facts."""
    if not body:
        return []
    known_facts = " ".join(
        str(value or "")
        for product in products
        for value in (
            product.get("product_name"),
            product.get("product_no"),
            product.get("specs"),
            product.get("series"),
            product.get("material"),
            product.get("material_description"),
            product.get("colors"),
            product.get("description"),
            *(product.get("attributes") or {}).values(),
        )
    ).casefold()
    matches = _PRODUCT_PARAMETER_PATTERN.findall(body)
    if any(
        match.casefold().replace(" ", "") not in known_facts.replace(" ", "")
        for match in matches
    ):
        return ["正文含未在所选 PIM 产品资料中核验的尺寸、价格或保修参数"]
    return []


class ContentGenerationError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


class ContentService:
    def __init__(
        self,
        adapter: AIServiceAdapter,
        db: AsyncSession,
        *,
        model: str,
        skill: ContentSkill | None = None,
    ):
        self.adapter = adapter
        self.db = db
        self.model = model
        self.skill = skill

    async def _load_adopted_topic_item(
        self,
        topic_item_id: UUID,
        current_user: dict[str, Any],
    ) -> ContentTopicItem:
        """Load a topic item that this request is allowed to consume.

        Content topic items follow the same full-scope rule as the other
        Content* models, but the scope predicate is still applied here so a
        future narrower content scope cannot turn this foreign-key-like input
        into an access-control bypass.
        """
        user_id = None
        raw_user_id = current_user.get("sub")
        if raw_user_id:
            try:
                user_id = UUID(str(raw_user_id))
            except (TypeError, ValueError):
                pass
        role_code = current_user.get("role_code") or "operator"

        stmt = (
            select(ContentTopicItem)
            .join(ContentTopicRun, ContentTopicRun.id == ContentTopicItem.run_id)
            .where(
                ContentTopicItem.id == topic_item_id,
                ContentTopicItem.status == "adopted",
                ContentTopicItem.is_deleted.is_(False),
                ContentTopicRun.is_deleted.is_(False),
            )
            .with_for_update(of=ContentTopicItem)
        )
        stmt = apply_data_scope(
            stmt,
            user_id=user_id,
            role_code=role_code,
            model=ContentTopicItem,
        )
        result = await self.db.execute(stmt)
        topic_item = result.scalar_one_or_none()
        if topic_item is None or topic_item.status != "adopted":
            raise ContentGenerationError(40401, "选题不存在、不可见或尚未采纳")
        if topic_item.content_batch_id is None:
            raise ContentGenerationError(40010, "已采纳选题缺少预建内容批次，请重新采纳")
        return topic_item

    async def generate(
        self,
        body: Any,
        current_user: dict[str, Any],
    ) -> dict[str, Any]:
        user_id = None
        raw_user_id = current_user.get("sub")
        if raw_user_id:
            try:
                user_id = UUID(str(raw_user_id))
            except (TypeError, ValueError):
                raise ContentGenerationError(40101, "当前用户标识无效") from None

        topic_item: ContentTopicItem | None = None
        batch: ContentBatch | None = None
        if body.topic_item_id is not None:
            topic_item = await self._load_adopted_topic_item(
                body.topic_item_id,
                current_user,
            )
            batch_result = await self.db.execute(
                select(ContentBatch).where(
                    ContentBatch.id == topic_item.content_batch_id,
                    ContentBatch.is_deleted.is_(False),
                ).with_for_update(of=ContentBatch)
            )
            batch = batch_result.scalar_one_or_none()
            if batch is None:
                raise ContentGenerationError(40010, "选题预建内容批次不存在")
            if batch.status not in {"pending", "failed"}:
                raise ContentGenerationError(40010, "选题预建内容批次已生成或正在生成")

        generation_product_ids = list(body.product_ids)
        if not generation_product_ids and batch is not None:
            try:
                generation_product_ids = [
                    UUID(str(pid)) for pid in (batch.product_ids or [])
                ]
            except (TypeError, ValueError):
                raise ContentGenerationError(40010, "选题预建批次的产品数据无效") from None

        products: list[dict] = []
        if generation_product_ids:
            stmt = (
                select(Product)
                .where(
                    Product.id.in_(generation_product_ids),
                    Product.is_deleted.is_(False),
                )
                .options(*PRODUCT_FACT_OPTIONS)
            )
            result = await self.db.execute(stmt)
            for p in result.scalars():
                products.append(product_fact_payload(p))

        project_facts: list[dict[str, Any]] = []
        project_fact_gap = False
        if body.project_id is not None:
            role_code = current_user.get("role_code") or "operator"
            project_stmt = select(Project).where(
                Project.id == body.project_id,
                Project.is_deleted.is_(False),
            )
            project_stmt = apply_data_scope(
                project_stmt,
                user_id=user_id,
                role_code=role_code,
                model=Project,
            )
            project_result = await self.db.execute(project_stmt)
            project = project_result.scalar_one_or_none()
            if project is None:
                project_fact_gap = True
            else:
                # Exclude remarks, customer identity, budgets, dialogue and other
                # potentially sensitive fields from external content prompts.
                project_facts.append(
                    {
                        "project_type": project.project_type,
                        "stage": project.stage,
                        "status": project.status,
                    }
                )

        if batch is None:
            batch = ContentBatch(
                title=body.title,
                customer_id=body.customer_id,
                project_id=body.project_id,
                product_ids=[str(pid) for pid in generation_product_ids],
                topic=body.topic,
                platform=body.platform,
                tone=body.tone,
                requested_count=body.requested_count,
                status="running",
                prompt_version=PROMPT_VERSION,
                created_by=user_id,
            )
            self.db.add(batch)
        else:
            # The batch created at topic adoption is the generation target.
            # Keep user edits from the workshop, but never create a second
            # batch and leave the adopted topic pointing at an unused one.
            batch.title = body.title
            batch.customer_id = body.customer_id
            batch.project_id = body.project_id
            batch.product_ids = [str(pid) for pid in generation_product_ids]
            batch.topic = body.topic
            batch.platform = body.platform
            batch.tone = body.tone
            batch.requested_count = body.requested_count
            batch.status = "running"
            batch.error_msg = None
            batch.updated_by = user_id
        batch.prompt_version = PROMPT_VERSION
        # Record the resolved model even if the upstream call or output fails;
        # this keeps failed batches traceable to the model that was used.
        batch.model_name = self.model
        await self.db.flush()

        start = time.perf_counter()
        if self.skill is not None:
            prompt = build_content_prompt(
                self.skill,
                topic=batch.topic,
                platform=batch.platform,
                tone=batch.tone,
                products=products,
                project_facts=project_facts,
            )
        else:
            prompt = _build_generation_prompt(batch.topic, batch.platform, batch.tone, products)
        if self.skill is not None:
            batch.source_skill_code = self.skill.code

        try:
            try:
                resp = await self.adapter.chat(
                    session_id=f"content_gen:{batch.id}",
                    message=prompt,
                    history=[{"role": "system", "content": SYSTEM_PERSONA}],
                    stream=False,
                    model=self.model,
                )
            except TypeError as exc:
                # Keep the existing small fake adapters and third-party adapter
                # implementations compatible with the optional model override.
                if "model" not in str(exc):
                    raise
                resp = await self.adapter.chat(
                    session_id=f"content_gen:{batch.id}",
                    message=prompt,
                    history=[{"role": "system", "content": SYSTEM_PERSONA}],
                    stream=False,
                )
        except Exception as exc:
            batch.status = "failed"
            batch.error_msg = f"AI 服务调用失败（{type(exc).__name__}）"
            await self.db.flush()
            logger.warning("content AI call failed error_type=%s", type(exc).__name__)
            raise ContentGenerationError(50302, "AI 服务调用失败，请稍后重试") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        answer = resp.get("answer", "")

        try:
            raw = _extract_json(answer)
        except (json.JSONDecodeError, ValueError) as exc:
            batch.status = "failed"
            batch.error_msg = f"AI 返回格式错误: {exc}"[:500]
            batch.latency_ms = latency_ms
            await self.db.flush()
            raise ContentGenerationError(40001, "AI 输出不符合约定结构") from exc

        try:
            items_data = _validate_schema(raw, self.skill.output_schema if self.skill else None)
        except ValueError as exc:
            batch.status = "failed"
            batch.error_msg = str(exc)[:500]
            batch.latency_ms = latency_ms
            await self.db.flush()
            raise ContentGenerationError(40001, str(exc)) from exc

        if not items_data:
            batch.status = "failed"
            batch.error_msg = "AI 输出无有效条目"
            batch.latency_ms = latency_ms
            await self.db.flush()
            raise ContentGenerationError(40001, "AI 输出无有效条目")

        items: list[ContentItem] = []
        for _idx, item_data in enumerate(items_data):
            warnings = _check_compliance(
                f"{item_data['title']}\n{item_data['body']}"
            )
            warnings.extend(item_data.get("warnings", []))
            verified, matched, unmatched = _verify_mentioned_products(
                item_data.get("mentioned_products", []),
                products,
            )

            verified_payload = {
                "_verified_by": "products_api",
                "_verified_at": datetime.now(_BEIJING_TZ).isoformat(),
                "products": [{"name": n} for n in matched],
                "unmatched": unmatched,
            }
            verification_gaps = list(item_data.get("verification_gaps", []))
            verification_gaps.extend(
                _find_unverified_product_parameters(item_data["body"], products)
            )
            if unmatched:
                verification_gaps.append("提及的产品名称未在当前 PIM 产品资料中匹配")
            if not products:
                verification_gaps.append("未提供产品资料，产品相关事实待核验")
            if project_fact_gap:
                verification_gaps.append("所选项目资料不可用或不可见，相关事实待核验")
            verification_gaps = list(dict.fromkeys(verification_gaps))[:20]
            if verification_gaps:
                warnings.append("存在待核验资料，请完成核实后再采纳")

            item = ContentItem(
                batch_id=batch.id,
                item_type="copy",
                platform=batch.platform,
                title=item_data["title"],
                body=item_data["body"],
                hashtags=item_data["hashtags"],
                status="draft",
                verified_payload=verified_payload,
                warnings=warnings,
                verification_gaps=verification_gaps,
                model_provider="content-openai",
                model_name=(resp.get("model") if isinstance(resp, dict) else None) or self.model,
                generation_version=PROMPT_VERSION,
                source_skill_code=self.skill.code if self.skill else None,
                created_by=user_id,
            )
            self.db.add(item)
            items.append(item)

        batch.status = "done"
        batch.latency_ms = latency_ms
        batch.model_provider = "content-openai"
        batch.model_name = (resp.get("model") if isinstance(resp, dict) else None) or self.model
        batch.updated_by = user_id
        if topic_item is not None:
            topic_item.status = "used"
            topic_item.content_batch_id = batch.id
            topic_item.update_time = datetime.now(UTC)
            topic_item.updated_by = user_id
        await self.db.flush()

        return {"batch": batch, "items": items}

    async def publish_item(
        self,
        item_id: UUID,
        platform: str,
        publish_url: str,
        published_at: datetime | None,
        account_name: str | None,
        video_attachment_id: UUID | None,
        external_ref: str | None,
        current_user: dict[str, Any],
    ) -> ContentPublication:
        result = await self.db.execute(
            select(ContentItem).where(
                ContentItem.id == item_id,
                ContentItem.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ContentGenerationError(40401, "内容条目不存在")

        if item.status != "produced" and item.status != "adopted":
            raise ContentGenerationError(40010, f"非法状态迁移: {item.status} -> published")

        now = datetime.now(_BEIJING_TZ)
        if published_at is None:
            published_at = now

        pub = ContentPublication(
            content_item_id=item.id,
            platform=platform,
            account_name=account_name,
            publish_url=publish_url,
            published_at=published_at,
            video_attachment_id=video_attachment_id,
            external_ref=external_ref,
            created_by=UUID(current_user["sub"]) if current_user.get("sub") else None,
        )
        self.db.add(pub)
        await self.db.flush()

        item.status = "published"
        item.published_at = published_at
        await self.db.flush()

        await self._create_r2_reminders(pub, current_user)
        await self._close_reminders("content_publish_check", str(item.id))

        return pub

    async def _create_r2_reminders(
        self,
        publication: ContentPublication,
        current_user: dict[str, Any],
    ) -> None:
        user_id = current_user.get("sub")
        if not user_id:
            return

        for days in _R2_DAYS:
            rule_code = f"content_metric_t{days}"
            dedupe_key = f"content_metric:{publication.id}:t{days}"
            due_at = self._due_at_for(publication.published_at, days)

            reminder = Reminder(
                rule_code=rule_code,
                target_type="publication",
                target_id=publication.id,
                assignee_id=UUID(user_id),
                title=f"录入曝光数据 (T+{days})",
                body=f"请录入发布内容 T+{days} 的曝光数据",
                due_at=due_at,
                dedupe_key=dedupe_key,
                created_by=UUID(user_id),
            )
            self.db.add(reminder)

    def _due_at_for(self, base_utc: datetime, days: int, hour: int = 9) -> datetime:
        local = base_utc.astimezone(_BEIJING_TZ) + timedelta(days=days)
        local = local.replace(hour=hour, minute=0, second=0, microsecond=0)
        return local.astimezone(UTC)

    async def _close_reminders(self, rule_code: str, target_id: str) -> None:
        result = await self.db.execute(
            select(Reminder).where(
                Reminder.rule_code == rule_code,
                Reminder.target_id == UUID(target_id),
                Reminder.status.in_(["pending", "snoozed"]),
            )
        )
        for r in result.scalars():
            r.status = "done"
            r.done_at = datetime.now(UTC)

    async def upsert_metric(
        self,
        entry: MetricEntry,
        current_user: dict[str, Any],
    ) -> ContentMetricSnapshot:
        result = await self.db.execute(
            select(ContentPublication).where(
                ContentPublication.id == entry.publication_id,
                ContentPublication.is_deleted.is_(False),
            )
        )
        pub = result.scalar_one_or_none()
        if pub is None:
            raise ContentGenerationError(40401, "发布记录不存在")

        if entry.captured_date:
            captured_date = datetime.strptime(entry.captured_date, "%Y-%m-%d").date()
        elif entry.captured_at:
            captured_date = entry.captured_at.astimezone(_BEIJING_TZ).date()
        else:
            captured_date = datetime.now(_BEIJING_TZ).date()

        captured_at = entry.captured_at or datetime.now(UTC)

        result = await self.db.execute(
            select(ContentMetricSnapshot).where(
                ContentMetricSnapshot.publication_id == entry.publication_id,
                ContentMetricSnapshot.captured_date == captured_date,
                ContentMetricSnapshot.is_deleted.is_(False),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.views = entry.views
            existing.likes = entry.likes
            existing.comments = entry.comments
            existing.shares = entry.shares
            existing.favorites = entry.favorites
            existing.leads = entry.leads
            existing.captured_at = captured_at
            existing.source = entry.source
            existing.updated_by = UUID(current_user["sub"]) if current_user.get("sub") else None
            await self.db.flush()
            return existing

        snapshot = ContentMetricSnapshot(
            publication_id=entry.publication_id,
            views=entry.views,
            likes=entry.likes,
            comments=entry.comments,
            shares=entry.shares,
            favorites=entry.favorites,
            leads=entry.leads,
            captured_at=captured_at,
            captured_date=captured_date,
            source=entry.source,
            created_by=UUID(current_user["sub"]) if current_user.get("sub") else None,
        )
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

    async def get_display_state(self, item: ContentItem) -> str:
        result = await self.db.execute(
            select(ContentPublication).where(
                ContentPublication.content_item_id == item.id,
                ContentPublication.is_deleted.is_(False),
            )
        )
        publications = result.scalars().all()

        pub_ids = [p.id for p in publications]
        snapshots: list[Any] = []
        if pub_ids:
            result = await self.db.execute(
                select(ContentMetricSnapshot).where(
                    ContentMetricSnapshot.publication_id.in_(pub_ids),
                    ContentMetricSnapshot.is_deleted.is_(False),
                )
            )
            snapshots = result.scalars().all()

        reminders: list[Any] = []
        if pub_ids:
            result = await self.db.execute(
                select(Reminder).where(
                    Reminder.target_id.in_(pub_ids),
                    Reminder.rule_code.like("content_metric_t%"),
                )
            )
            reminders = result.scalars().all()

        return derive_display_state(item, publications, snapshots, reminders)
