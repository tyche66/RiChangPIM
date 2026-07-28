from __future__ import annotations

from app.knowledge.documents.base import KnowledgeChunkPayload, stable_content_hash


def estimate_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(stripped) // 4)


def chunk_text(
    text: str,
    *,
    target_tokens: int = 450,
    overlap_tokens: int = 60,
) -> list[KnowledgeChunkPayload]:
    stripped = text.strip()
    if not stripped:
        return []

    target_chars = max(300, target_tokens * 4)
    overlap_chars = max(0, overlap_tokens * 4)
    paragraphs = [part.strip() for part in stripped.split("\n") if part.strip()]
    if not paragraphs:
        paragraphs = [stripped]

    chunks: list[KnowledgeChunkPayload] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if current and len(candidate) > target_chars:
            chunks.append(_make_chunk(len(chunks), current))
            current = _overlap_tail(current, overlap_chars)
            candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        current = candidate

    if current:
        chunks.append(_make_chunk(len(chunks), current))
    return chunks


def _overlap_tail(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or len(text) <= overlap_chars:
        return text
    return text[-overlap_chars:].strip()


def _make_chunk(index: int, text: str) -> KnowledgeChunkPayload:
    normalized = " ".join(text.split())
    return KnowledgeChunkPayload(
        chunk_index=index,
        chunk_text=text,
        chunk_type="text",
        section_path=f"chunk/{index}",
        token_count=estimate_tokens(text),
        normalized_text=normalized,
        content_hash=stable_content_hash({"index": index, "text": normalized}),
    )
