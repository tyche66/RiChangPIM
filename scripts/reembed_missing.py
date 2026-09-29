#!/usr/bin/env python3
"""Backfill missing knowledge_chunk embeddings and rebuild unindexed manuals.

Covers two gap classes in the production ai_pim DB:

  1. knowledge_chunk rows with ``embedding IS NULL`` on active, indexed documents.
     Such chunks are invisible to ``retrieval/vector.py`` (it filters on
     ``embedding IS NOT NULL``), so the corresponding products silently drop
     out of the vector recall channel.
  2. ``product_manual`` rows with ``index_status IN ('pending','failed')`` and
     zero active ``knowledge_chunk`` rows — the pipeline never ran for them.

Reuses the app's own embedding path (``get_ai_adapter()`` + the same model the
existing vectors use), so new vectors land in the exact same space.

Usage (inside the backend container, where env is already loaded):

    python scripts/reembed_missing.py --dry-run
    python scripts/reembed_missing.py
    python scripts/reembed_missing.py --no-manuals
    python scripts/reembed_missing.py --orphans delete

Environment:
    DATABASE_URL, AI_ADAPTER, AI_EMBEDDING_MODEL, AI_EMBEDDING_DIM,
    AI_EMBEDDING_API_URL, AI_EMBEDDING_API_KEY
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.adapters.exceptions import AIAdapterError, AIAdapterUnavailableError
from app.adapters.factory import get_ai_adapter
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.knowledge.indexing.pipeline import KnowledgeIndexingPipeline
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.product import Product, ProductManual

BATCH_SIZE = 96
MAX_RETRIES = 3
RETRY_BASE_SLEEP = 2.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _embed_with_retry(adapter, texts: list[str], *, label: str) -> list[list[float]]:
    """Wrap ``adapter.embed`` with exponential backoff on transient failures."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await adapter.embed(texts)
        except AIAdapterError as exc:
            last_exc = exc
            if attempt == MAX_RETRIES:
                raise
            sleep_s = RETRY_BASE_SLEEP * (2 ** (attempt - 1))
            print(
                f"    {label}: attempt {attempt}/{MAX_RETRIES} failed "
                f"({type(exc).__name__}), retry in {sleep_s:.1f}s",
                flush=True,
            )
            await asyncio.sleep(sleep_s)
    assert last_exc is not None
    raise last_exc


async def _fetch_missing_chunks() -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeChunk.is_deleted.is_(False),
                KnowledgeChunk.embedding.is_(None),
                KnowledgeDocument.is_deleted.is_(False),
            )
            .order_by(KnowledgeChunk.create_time)
        )
        return list(result.all())


async def _find_unindexed_manuals() -> list[ProductManual]:
    """Manuals whose pipeline never produced a knowledge_document."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProductManual)
            .where(
                ProductManual.is_deleted.is_(False),
                ProductManual.index_status.in_(("pending", "failed", "processing")),
            )
            .order_by(ProductManual.create_time)
        )
        manuals = list(result.scalars().all())
        for manual in manuals:
            doc_result = await db.execute(
                select(KnowledgeDocument.id).where(
                    KnowledgeDocument.source_type == "product_manual",
                    KnowledgeDocument.source_id == manual.id,
                    KnowledgeDocument.is_deleted.is_(False),
                )
            )
            if doc_result.scalar_one_or_none() is not None:
                manuals.remove(manual)
    return manuals


async def _products_gone(db, product_ids: list[str]) -> set[str]:
    out: set[str] = set()
    for pid in set(product_ids):
        if not pid:
            out.add(pid)
            continue
        product = await db.get(Product, pid)
        if product is None or product.is_deleted:
            out.add(pid)
    return out


async def _soft_delete_doc(db, doc: KnowledgeDocument) -> int:
    now = datetime.now(UTC)
    doc.is_deleted = True
    doc.deleted_at = now
    doc.update_time = now
    chunks = (
        await db.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_id == doc.id,
                KnowledgeChunk.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    for chunk in chunks:
        chunk.is_deleted = True
        chunk.deleted_at = now
    await db.flush()
    return len(chunks)


# ---------------------------------------------------------------------------
# phase A — backfill missing embeddings
# ---------------------------------------------------------------------------


async def phase_backfill(
    *,
    dry_run: bool,
    orphans_policy: str,
    limit: int | None,
) -> dict[str, int]:
    rows = await _fetch_missing_chunks()
    if not rows:
        print("Phase A: no active chunks missing embeddings.")
        return {
            "total": 0,
            "embedded": 0,
            "skipped_orphan": 0,
            "soft_deleted": 0,
            "errors": 0,
            "remaining": 0,
        }

    docs = {doc.id for _, doc in rows}
    print(
        f"Phase A: {len(rows)} active chunk(s) missing embedding across {len(docs)} doc(s)."
        f" model={settings.AI_EMBEDDING_MODEL!r} dim={settings.AI_EMBEDDING_DIM}"
    )

    async with AsyncSessionLocal() as db:
        orphan_ids = await _products_gone(
            db, [doc.product_id for _, doc in rows if doc.product_id]
        )
        if orphan_ids:
            print(f"  {len(orphan_ids)} doc(s) reference a deleted/missing product (orphan).")

    orphan_doc_ids = {doc.id for _, doc in rows if doc.product_id in orphan_ids}

    to_embed: list[tuple[KnowledgeChunk, KnowledgeDocument, str]] = []
    orphan_skip = 0
    for chunk, doc in rows:
        if doc.id in orphan_doc_ids:
            orphan_skip += 1
            continue
        text = chunk.normalized_text or chunk.chunk_text
        if not text:
            orphan_skip += 1
            continue
        to_embed.append((chunk, doc, text))

    if limit is not None:
        to_embed = to_embed[:limit]

    if dry_run:
        print(
            f"  DRY RUN: would embed {len(to_embed)} chunk(s); "
            f"skip {orphan_skip} orphan chunk(s) (policy={orphans_policy})."
        )
        for chunk, doc, text in to_embed[:3]:
            print(f"    doc={doc.id} chunk={chunk.id} text={text[:100]!r}")
        return {
            "total": len(rows),
            "embedded": len(to_embed),
            "skipped_orphan": orphan_skip,
            "soft_deleted": 0,
            "errors": 0,
            "remaining": len(rows),
        }

    # Execute: commit orphans first if policy=delete.
    soft_deleted = 0
    if orphans_policy == "delete" and orphan_doc_ids:
        async with AsyncSessionLocal() as db:
            for doc_id in orphan_doc_ids:
                doc = await db.get(KnowledgeDocument, doc_id)
                if doc is None or doc.is_deleted:
                    continue
                await _soft_delete_doc(db, doc)
                soft_deleted += 1
            await db.commit()
        print(f"  soft-deleted {soft_deleted} orphan doc(s).")

    adapter = get_ai_adapter()
    if not getattr(adapter, "available", True):
        raise AIAdapterUnavailableError("AI adapter unavailable; cannot backfill embeddings.")
    model_name = settings.AI_EMBEDDING_MODEL
    model_version = settings.AI_EMBEDDING_VERSION or model_name

    errors = 0
    t0 = time.time()
    for i in range(0, len(to_embed), BATCH_SIZE):
        batch = to_embed[i : i + BATCH_SIZE]
        texts = [t for _, _, t in batch]
        batch_no = i // BATCH_SIZE
        try:
            vecs = await _embed_with_retry(adapter, texts, label=f"batch {batch_no}")
        except AIAdapterError as exc:
            print(f"  batch {batch_no} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            errors += len(batch)
            continue

        if len(vecs) != len(texts):
            print(
                f"  batch {batch_no} FAILED: expected {len(texts)} vectors, got {len(vecs)}",
                file=sys.stderr,
            )
            errors += len(batch)
            continue

        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC)
            # Re-fetch inside THIS session: the chunk/doc objects were loaded in a
            # different (now closed) session and SQLAlchemy will not track
            # changes to detached instances. Without this the commit is a no-op.
            written = 0
            for (chunk, doc, _), vec in zip(batch, vecs, strict=True):
                c = await db.get(KnowledgeChunk, chunk.id)
                d = await db.get(KnowledgeDocument, doc.id)
                if c is None or d is None:
                    continue
                c.embedding = vec
                c.embedding_model = model_name
                c.embedding_version = model_version
                d.last_indexed_at = now
                d.index_status = "indexed"
                d.update_time = now
                written += 1
            await db.commit()
        elapsed = time.time() - t0
        done = min(i + BATCH_SIZE, len(to_embed))
        print(
            f"  batch {batch_no}: wrote {written} embedding(s) "
            f"({done}/{len(to_embed)}, {elapsed:.1f}s)"
        )

    verify = await _fetch_missing_chunks()
    print(
        f"  VERIFY: {len(verify)} active chunk(s) still missing embedding "
        f"(expected {max(len(rows) - (len(to_embed) - errors) - orphan_skip, 0)})"
    )
    print(
        f"Phase A done: embedded={len(to_embed) - errors} errors={errors} "
        f"skipped_orphan={orphan_skip} soft_deleted={soft_deleted} "
        f"elapsed={time.time() - t0:.1f}s"
    )
    return {
        "total": len(rows),
        "embedded": len(to_embed) - errors,
        "skipped_orphan": orphan_skip,
        "soft_deleted": soft_deleted,
        "errors": errors,
        "remaining": len(verify),
    }


# ---------------------------------------------------------------------------
# phase B — rebuild unindexed manuals
# ---------------------------------------------------------------------------


async def phase_manuals(*, dry_run: bool) -> dict[str, int]:
    manuals = await _find_unindexed_manuals()
    if not manuals:
        print("Phase B: no unindexed product_manual rows.")
        return {"total": 0, "indexed": 0, "blocked": 0}

    print(f"Phase B: {len(manuals)} product_manual row(s) without knowledge_document:")
    for m in manuals:
        parsed = (m.parsed_content or "").strip()
        print(
            f"  id={m.id} status={m.index_status!r} parse={m.parse_status!r} "
            f"parsed_len={len(parsed)} err={m.index_error!r}"
        )

    if dry_run:
        print(f"  DRY RUN: would rebuild {len(manuals)} manual(s).")
        return {"total": len(manuals), "indexed": len(manuals), "blocked": 0}

    adapter = get_ai_adapter()
    if not getattr(adapter, "available", True):
        raise AIAdapterUnavailableError("AI adapter unavailable; cannot rebuild manuals.")
    indexed = 0
    blocked = 0
    for manual in manuals:
        async with AsyncSessionLocal() as db:
            fresh = await db.get(ProductManual, manual.id)
            if fresh is None or fresh.is_deleted:
                continue
            try:
                pipeline = KnowledgeIndexingPipeline(db)
                doc = await pipeline.upsert_source("product_manual", fresh.id)
                now = datetime.now(UTC)
                fresh.index_status = "indexed"
                fresh.last_indexed_at = now
                fresh.update_time = now
                fresh.index_error = None
                await db.commit()
                indexed += 1
                print(f"  OK manual={fresh.id} -> doc={doc.id}")
            except Exception as exc:  # noqa: BLE001 - we want to report, not crash the loop
                await db.rollback()
                blocked += 1
                fresh.index_status = "failed"
                fresh.index_error = str(exc).splitlines()[0][:240]
                fresh.update_time = datetime.now(UTC)
                await db.commit()
                print(f"  BLOCKED manual={fresh.id}: {fresh.index_error}")

    print(
        f"Phase B done: indexed={indexed} blocked={blocked} total={len(manuals)}"
    )
    return {"total": len(manuals), "indexed": indexed, "blocked": blocked}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="print the plan, do not write")
    p.add_argument("--no-manuals", action="store_true", help="skip phase B (manual rebuild)")
    p.add_argument(
        "--orphans",
        choices=("skip", "delete"),
        default="skip",
        help="policy for chunks whose product was deleted (default: skip)",
    )
    p.add_argument("--limit", type=int, default=None, help="max chunks to embed in phase A")
    return p.parse_args(argv)


async def _run() -> int:
    args = parse_args(sys.argv[1:])
    print(
        f"settings: DATABASE_URL={settings.DATABASE_URL.split('@')[-1]} "
        f"model={settings.AI_EMBEDDING_MODEL} dim={settings.AI_EMBEDDING_DIM}"
    )
    print(f"mode: dry_run={args.dry_run} orphans={args.orphans} limit={args.limit}")

    phase_a = await phase_backfill(
        dry_run=args.dry_run,
        orphans_policy=args.orphans,
        limit=args.limit,
    )
    print()
    if args.no_manuals:
        phase_b: dict[str, int] = {"total": 0, "indexed": 0, "blocked": 0}
    else:
        phase_b = await phase_manuals(dry_run=args.dry_run)

    summary = {"phase_a": phase_a, "phase_b": phase_b}
    print()
    print("SUMMARY")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    ok = phase_a["errors"] == 0 and phase_b["blocked"] == 0
    if not args.dry_run and phase_a.get("remaining", 0) > 0:
        ok = False
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        rc = asyncio.run(_run())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        rc = 130
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        rc = 1
    sys.exit(rc)
