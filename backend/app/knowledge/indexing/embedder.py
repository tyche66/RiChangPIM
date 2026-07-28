from __future__ import annotations

from app.adapters.base import AIServiceAdapter
from app.knowledge.documents.base import KnowledgeChunkPayload
from app.knowledge.indexing.embedding_cache import embed_texts_cached


async def embed_chunks(
    adapter: AIServiceAdapter,
    chunks: list[KnowledgeChunkPayload],
    *,
    model_name: str,
    model_version: str,
) -> list[KnowledgeChunkPayload]:
    if not chunks:
        return []
    vectors = await embed_texts_cached(
        adapter,
        [chunk.normalized_text or chunk.chunk_text for chunk in chunks],
        model_name=model_name,
        model_version=model_version,
    )
    if len(vectors) != len(chunks):
        raise ValueError("embedding count does not match chunk count")

    embedded: list[KnowledgeChunkPayload] = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        final = chunk.finalized()
        final.embedding = vector
        final.embedding_model = model_name
        final.embedding_version = model_version
        embedded.append(final)
    return embedded
