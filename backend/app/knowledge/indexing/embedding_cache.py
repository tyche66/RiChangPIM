from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Protocol

from app.adapters.base import AIServiceAdapter
from app.core.config import settings


class EmbeddingAdapter(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_one(self, text: str) -> list[float]: ...


@dataclass
class _CacheEntry:
    vector: list[float]
    expires_at: float


class InMemoryEmbeddingCache:
    def __init__(self) -> None:
        self._items: dict[str, _CacheEntry] = {}

    def get_many(self, keys: list[str]) -> dict[int, list[float]]:
        now = time.monotonic()
        hits: dict[int, list[float]] = {}
        expired: list[str] = []
        for idx, key in enumerate(keys):
            entry = self._items.get(key)
            if not entry:
                continue
            if entry.expires_at <= now:
                expired.append(key)
                continue
            hits[idx] = list(entry.vector)
        for key in expired:
            self._items.pop(key, None)
        return hits

    def set_many(self, values: dict[str, list[float]], *, ttl_seconds: int, max_items: int) -> None:
        if ttl_seconds <= 0 or max_items <= 0:
            return
        expires_at = time.monotonic() + ttl_seconds
        for key, vector in values.items():
            self._items[key] = _CacheEntry(vector=list(vector), expires_at=expires_at)
        overflow = len(self._items) - max_items
        if overflow > 0:
            for key in list(self._items)[:overflow]:
                self._items.pop(key, None)

    def clear(self) -> None:
        self._items.clear()


_cache = InMemoryEmbeddingCache()


async def embed_texts_cached(
    adapter: AIServiceAdapter,
    texts: list[str],
    *,
    model_name: str,
    model_version: str,
) -> list[list[float]]:
    if not texts:
        return []
    if not settings.AI_EMBEDDING_CACHE_ENABLED:
        return await adapter.embed(texts)

    keys = [_cache_key(model_name, model_version, text) for text in texts]
    hits = _cache.get_many(keys)
    missing_indexes = [idx for idx in range(len(texts)) if idx not in hits]
    if not missing_indexes:
        return [hits[idx] for idx in range(len(texts))]

    missing_vectors = await adapter.embed([texts[idx] for idx in missing_indexes])
    if len(missing_vectors) != len(missing_indexes):
        return await adapter.embed(texts)

    _cache.set_many(
        {keys[idx]: vector for idx, vector in zip(missing_indexes, missing_vectors, strict=True)},
        ttl_seconds=settings.AI_EMBEDDING_CACHE_TTL_SECONDS,
        max_items=settings.AI_EMBEDDING_CACHE_MAX_ITEMS,
    )
    merged = dict(hits)
    for idx, vector in zip(missing_indexes, missing_vectors, strict=True):
        merged[idx] = list(vector)
    return [merged[idx] for idx in range(len(texts))]


async def embed_one_cached(
    adapter: AIServiceAdapter,
    text: str,
    *,
    model_name: str,
    model_version: str,
) -> list[float]:
    vectors = await embed_texts_cached(
        adapter,
        [text],
        model_name=model_name,
        model_version=model_version,
    )
    return vectors[0] if vectors else []


def clear_embedding_cache() -> None:
    _cache.clear()


def _cache_key(model_name: str, model_version: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{model_name}|{model_version}|{digest}"
