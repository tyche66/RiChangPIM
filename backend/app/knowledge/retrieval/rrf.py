from __future__ import annotations


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[dict]],
    *,
    k: int = 60,
) -> list[dict]:
    scores: dict[str, float] = {}
    merged: dict[str, dict] = {}
    for channel, rows in ranked_lists.items():
        for rank, row in enumerate(rows, start=1):
            key = str(row.get("source_id") or row.get("chunk_id") or row.get("document_id"))
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            existing = merged.get(key, {}).copy()
            candidate = row.copy()
            channels = set(existing.get("channels") or []) | {channel}
            candidate.update(existing)
            candidate.update(row)
            candidate["rrf_score"] = scores[key]
            candidate["channels"] = sorted(channels)
            merged[key] = candidate
    return sorted(merged.values(), key=lambda item: item.get("rrf_score", 0.0), reverse=True)
