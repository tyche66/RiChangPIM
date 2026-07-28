from __future__ import annotations

import pytest

from app.core.config import settings
from app.knowledge.indexing.embedding_cache import (
    clear_embedding_cache,
    embed_one_cached,
    embed_texts_cached,
)


class FakeEmbeddingAdapter:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text)), float(idx)] for idx, text in enumerate(texts)]

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    clear_embedding_cache()
    monkeypatch.setattr(settings, "AI_EMBEDDING_CACHE_TTL_SECONDS", 3600)
    monkeypatch.setattr(settings, "AI_EMBEDDING_CACHE_MAX_ITEMS", 100)
    yield
    clear_embedding_cache()


@pytest.mark.anyio
async def test_embedding_cache_disabled_calls_adapter_each_time(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMBEDDING_CACHE_ENABLED", False)
    adapter = FakeEmbeddingAdapter()

    await embed_texts_cached(adapter, ["same"], model_name="m", model_version="v1")
    await embed_texts_cached(adapter, ["same"], model_name="m", model_version="v1")

    assert adapter.calls == [["same"], ["same"]]


@pytest.mark.anyio
async def test_embedding_cache_reuses_same_model_version(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMBEDDING_CACHE_ENABLED", True)
    adapter = FakeEmbeddingAdapter()

    first = await embed_one_cached(adapter, "same", model_name="m", model_version="v1")
    second = await embed_one_cached(adapter, "same", model_name="m", model_version="v1")

    assert first == second
    assert adapter.calls == [["same"]]


@pytest.mark.anyio
async def test_embedding_cache_isolated_by_model_version(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMBEDDING_CACHE_ENABLED", True)
    adapter = FakeEmbeddingAdapter()

    await embed_one_cached(adapter, "same", model_name="m", model_version="v1")
    await embed_one_cached(adapter, "same", model_name="m", model_version="v2")

    assert adapter.calls == [["same"], ["same"]]
