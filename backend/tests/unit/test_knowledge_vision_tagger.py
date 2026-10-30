"""产品图视觉标注：解析、跳过条件与「只标一次」的行为。"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.knowledge.vision import tagger as tagger_module
from app.knowledge.vision.tagger import MAX_TAGGED_IMAGES, ProductImageVisionTagger, _parse_tags


class _FakeDb:
    def __init__(self):
        self.flushes = 0

    async def flush(self):
        self.flushes += 1


class _FakeAdapter:
    def __init__(self, reply='["圆形会议桌", "木质桌面", "圆形会议桌"]'):
        self.reply = reply
        self.calls: list[dict] = []

    async def vision_chat(self, image_url, prompt, *, model=None):
        self.calls.append({"image_url": image_url, "model": model})
        return self.reply


def _image(*, cover=False, sort=0, vision_tags=None):
    return SimpleNamespace(
        id=uuid4(),
        is_deleted=False,
        is_cover=cover,
        sort=sort,
        vision_tags=vision_tags,
        attachment=SimpleNamespace(
            id=uuid4(), is_deleted=False, oss_key="k.jpg", file_name="k.jpg"
        ),
    )


def _configure(monkeypatch, vision_model="vision-1"):
    monkeypatch.setattr(
        tagger_module, "get_config", lambda _scope: SimpleNamespace(vision_model=vision_model)
    )


def _stub_download(monkeypatch):
    monkeypatch.setattr(
        ProductImageVisionTagger,
        "_data_url",
        lambda self, attachment: "data:image/jpeg;base64,AAAA",
    )


def test_parse_tags_accepts_json_array_and_dedupes():
    assert _parse_tags('```json\n["圆形会议桌","木质桌面","圆形会议桌"]\n```') == [
        "圆形会议桌",
        "木质桌面",
    ]


def test_parse_tags_falls_back_to_separator_split():
    assert _parse_tags("圆形会议桌、木质桌面\n会议室") == ["圆形会议桌", "木质桌面", "会议室"]


@pytest.mark.asyncio
async def test_skips_when_no_vision_model(monkeypatch):
    _configure(monkeypatch, vision_model=None)
    adapter = _FakeAdapter()
    images = [_image(vision_tags=["已有标签"])]
    tags = await ProductImageVisionTagger(_FakeDb(), adapter=adapter).ensure_product_tags(images)
    assert tags == ["已有标签"]
    assert adapter.calls == []
    assert images[0].vision_tags == ["已有标签"]


@pytest.mark.asyncio
async def test_tags_missing_images_once_and_reuses_cache(monkeypatch):
    _configure(monkeypatch)
    _stub_download(monkeypatch)
    adapter = _FakeAdapter()
    db = _FakeDb()
    cover = _image(cover=True)
    extra = _image(sort=2)
    images = [extra, cover]

    tags = await ProductImageVisionTagger(db, adapter=adapter).ensure_product_tags(images)

    assert tags == ["圆形会议桌", "木质桌面"]
    assert len(adapter.calls) == 2
    assert adapter.calls[0]["model"] == "vision-1"
    assert cover.vision_tags == ["圆形会议桌", "木质桌面"]
    assert db.flushes == 1

    # 第二次构建卡片时不应再调用模型（vision_tags 已落库）。
    adapter.calls.clear()
    again = await ProductImageVisionTagger(db, adapter=adapter).ensure_product_tags(images)
    assert again == tags
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_only_covers_first_images(monkeypatch):
    _configure(monkeypatch)
    _stub_download(monkeypatch)
    adapter = _FakeAdapter()
    images = [_image(sort=index) for index in range(MAX_TAGGED_IMAGES + 2)]

    await ProductImageVisionTagger(_FakeDb(), adapter=adapter).ensure_product_tags(images)

    assert len(adapter.calls) == MAX_TAGGED_IMAGES
