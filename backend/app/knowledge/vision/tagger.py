"""产品图视觉标注。

产品经理输入的是「产品名 + 材质 + 尺寸」，而买家用的是「圆形会议桌」「带轮」
「可折叠」这类外观词。这些词在结构化字段里根本不存在，向量检索自然命中不了。
这里让视觉模型看一遍产品图，产出 3–8 个外观/结构标签，写回
``product_image.vision_tags``，再由产品知识卡片并进 facts 参与建向量。

调用时机：知识卡片构建（索引 worker）里按需标注 —— 只有真的在建向量时才花
这次视觉调用；没有配置 ``vision_model`` 时整条链路静默跳过，不报错、不落脏数据。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import re

from app.adapters.none import NoneAdapter
from app.core.config import settings
from app.core.minio_client import get_minio_client
from app.services.ai_config import get_config

logger = logging.getLogger(__name__)

#: 每个产品最多标注几张图。主图 + 前两张细节图足够覆盖外观特征，
#: 十张图逐个调模型只会把索引任务的耗时和成本翻几倍。
MAX_TAGGED_IMAGES = 3

#: 单张图最大字节数。视觉模型对超大图也是先缩放，传原图纯属浪费带宽。
MAX_IMAGE_BYTES = 8 * 1024 * 1024

VISION_PROMPT = (
    "你是家具/办公用品的商品图识别助手。请观察这张产品图，输出 3-8 个"
    "用于检索的中文标签，覆盖：形状（如 圆形、弧形）、结构（如 带轮、可折叠）、"
    "桌面/材质观感（如 木质、玻璃）、使用场景（如 会议室、办公）。"
    "只输出 JSON 数组，例如 [\"圆形会议桌\",\"木质桌面\",\"会议室\"]，"
    "不要输出解释、不要输出价格、品牌或任何图中无法确认的信息。"
)

_JSON_ARRAY_RE = re.compile(r"\[[^\]]*\]", re.DOTALL)
_SPLIT_RE = re.compile(r"[,，、;；\n]+")
MAX_TAGS = 12
MAX_TAG_LENGTH = 24


class ProductImageVisionTagger:
    """给产品图打视觉标签；没有视觉能力时什么也不做。"""

    def __init__(self, db, adapter=None):
        self.db = db
        self._adapter = adapter

    @property
    def adapter(self):
        if self._adapter is None:
            from app.adapters.factory import get_ai_adapter

            self._adapter = get_ai_adapter()
        return self._adapter

    async def ensure_product_tags(self, images) -> list[str]:
        """补齐缺失的标注，返回该产品全部已确认标签（去重排序）。"""
        ordered = self._ordered(images)
        config = get_config("knowledge")
        if not config.vision_model:
            return self._collect(ordered)
        adapter = self.adapter
        if adapter is None or isinstance(adapter, NoneAdapter):
            return self._collect(ordered)

        changed = False
        for image in ordered[:MAX_TAGGED_IMAGES]:
            if image.vision_tags is not None:
                continue
            attachment = getattr(image, "attachment", None)
            if attachment is None or attachment.is_deleted:
                continue
            tags = await self._describe(adapter, attachment, config.vision_model)
            if tags is None:
                continue
            image.vision_tags = tags
            changed = True
        if changed:
            await self.db.flush()
        return self._collect(ordered)

    # ---------- internals ----------
    @staticmethod
    def _ordered(images) -> list:
        return sorted(
            [img for img in (images or []) if not img.is_deleted],
            key=lambda img: (not img.is_cover, img.sort or 0),
        )

    @staticmethod
    def _collect(images) -> list[str]:
        tags: set[str] = set()
        for image in images:
            for tag in image.vision_tags or []:
                text = str(tag).strip()
                if text:
                    tags.add(text)
        return sorted(tags)

    async def _describe(self, adapter, attachment, model: str) -> list[str] | None:
        try:
            data_url = await asyncio.to_thread(self._data_url, attachment)
            if data_url is None:
                return None
            text = await adapter.vision_chat(data_url, VISION_PROMPT, model=model)
        except NotImplementedError:
            logger.info("AI 适配器不支持视觉标注，跳过产品图标注")
            return []
        except Exception as exc:  # noqa: BLE001 - 单张图失败不应让索引任务失败
            logger.warning(
                "产品图视觉标注失败 attachment=%s: %s", attachment.id, type(exc).__name__
            )
            return None
        return _parse_tags(text)

    def _data_url(self, attachment) -> str | None:
        client = get_minio_client()
        response = client.get_object(settings.MINIO_BUCKET, attachment.oss_key)
        try:
            data = response.read(MAX_IMAGE_BYTES + 1)
        finally:
            response.close()
            response.release_conn()
        if not data or len(data) > MAX_IMAGE_BYTES:
            return None
        mime = mimetypes.guess_type(attachment.file_name or "")[0] or "image/jpeg"
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{encoded}"


def _parse_tags(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    candidates: list[str] = []
    match = _JSON_ARRAY_RE.search(raw)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                candidates = [str(item) for item in parsed]
        except json.JSONDecodeError:
            candidates = []
    if not candidates:
        # 模型没按 JSON 输出时退化成按分隔符切，总比整条标注丢掉好。
        candidates = _SPLIT_RE.split(raw)

    tags: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        tag = item.strip().strip("\"'[]").strip()
        if not tag or len(tag) > MAX_TAG_LENGTH or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
        if len(tags) >= MAX_TAGS:
            break
    return tags
