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
from app.core.config import settings
from app.models.content import (
    ContentBatch,
    ContentItem,
    ContentMetricSnapshot,
    ContentPublication,
)
from app.models.product import Product
from app.models.reminder import Reminder
from app.schemas.content import MetricEntry
from app.services.content_state import derive_display_state

logger = logging.getLogger(__name__)

_BEIJING_TZ = timezone(timedelta(hours=8))

_COMMIT_PATTERN = re.compile(r"\d+\s*元|￥\d+|最低|保证\d+天")

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

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["items"],
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["title", "body", "hashtags"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "maxLength": 60},
                    "body": {"type": "string", "minLength": 30, "maxLength": 2000},
                    "hashtags": {
                        "type": "array",
                        "maxItems": 10,
                        "items": {"type": "string", "maxLength": 20},
                    },
                    "mentioned_products": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 120},
                    },
                },
            },
        }
    },
}


def _build_generation_prompt(
    topic: str,
    platform: str,
    tone: str | None,
    products: list[dict],
) -> str:
    product_facts = []
    for p in products:
        fact = {
            "name": p.get("product_name", ""),
            "specs": p.get("specs", ""),
            "series": p.get("series", ""),
        }
        product_facts.append(fact)

    prompt = f"""你是新媒体内容创作助手。请根据以下信息生成内容。

主题：{topic}
平台：{platform}
风格：{tone or "不限"}

可引用的产品事实（仅限以下信息，禁止编造）：
{json.dumps(product_facts, ensure_ascii=False, indent=2)}

要求：
1. 输出严格符合 JSON Schema（items 数组，每条含 title/body/hashtags）
2. 禁止输出价格/折扣/交期/库存承诺
3. 禁止输出客户/项目/对话等隐私信息
4. 内容需符合广告法，避免极限词
5. mentioned_products 只能引用上述产品事实中的产品名称

输出格式：
{json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)}"""
    return prompt


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    return json.loads(text)


def _validate_schema(data: dict[str, Any]) -> list[dict[str, Any]]:
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

        validated.append({
            "title": title,
            "body": body,
            "hashtags": hashtags,
            "mentioned_products": mentioned,
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
    ):
        self.adapter = adapter
        self.db = db
        self.model = model

    async def generate(
        self,
        body: Any,
        current_user: dict[str, Any],
    ) -> dict[str, Any]:
        products: list[dict] = []
        if body.product_ids:
            stmt = select(Product).where(
                Product.id.in_(body.product_ids),
                Product.is_deleted.is_(False),
            )
            result = await self.db.execute(stmt)
            for p in result.scalars():
                products.append({
                    "id": str(p.id),
                    "product_name": p.product_name,
                    "specs": getattr(p, "specs", None),
                    "series": getattr(p, "series", None),
                })

        batch = ContentBatch(
            title=body.title,
            customer_id=body.customer_id,
            project_id=body.project_id,
            product_ids=[str(pid) for pid in body.product_ids],
            topic=body.topic,
            platform=body.platform,
            tone=body.tone,
            requested_count=body.requested_count,
            status="running",
            prompt_version=PROMPT_VERSION,
            created_by=UUID(current_user["sub"]) if current_user.get("sub") else None,
        )
        self.db.add(batch)
        await self.db.flush()

        start = time.perf_counter()
        prompt = _build_generation_prompt(
            body.topic, body.platform, body.tone, products
        )

        try:
            resp = await self.adapter.chat(
                session_id=f"content_gen:{batch.id}",
                message=prompt,
                history=[{"role": "system", "content": "你是新媒体内容创作助手。"}],
                stream=False,
            )
        except Exception as exc:
            batch.status = "failed"
            batch.error_msg = str(exc)[:500]
            await self.db.flush()
            raise ContentGenerationError(50302, f"AI 服务调用失败: {exc}") from exc

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
            items_data = _validate_schema(raw)
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

        user_id = UUID(current_user["sub"]) if current_user.get("sub") else None
        items: list[ContentItem] = []
        for _idx, item_data in enumerate(items_data):
            warnings = _check_compliance(item_data["body"])
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

            item = ContentItem(
                batch_id=batch.id,
                item_type="copy",
                platform=body.platform,
                title=item_data["title"],
                body=item_data["body"],
                hashtags=item_data["hashtags"],
                status="draft",
                verified_payload=verified_payload,
                warnings=warnings,
                model_provider=getattr(settings, "AI_ADAPTER", None),
                model_name=self.model,
                generation_version=PROMPT_VERSION,
                created_by=user_id,
            )
            self.db.add(item)
            items.append(item)

        batch.status = "done"
        batch.latency_ms = latency_ms
        batch.model_provider = getattr(settings, "AI_ADAPTER", None)
        batch.model_name = self.model
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
