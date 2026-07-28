from __future__ import annotations


def keep_top_chunks_per_document(rows: list[dict], *, limit_per_document: int = 3) -> list[dict]:
    counts: dict[str, int] = {}
    out: list[dict] = []
    for row in rows:
        document_id = str(row.get("document_id") or "")
        counts.setdefault(document_id, 0)
        if counts[document_id] >= limit_per_document:
            continue
        counts[document_id] += 1
        out.append(row)
    return out
