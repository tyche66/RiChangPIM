from __future__ import annotations

import pytest
from _db_probe import alembic_downgrade, alembic_upgrade, to_sync_url
from sqlalchemy import create_engine, text

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeIndexJob


def test_knowledge_models_import_cleanly():
    assert KnowledgeDocument.__tablename__ == "knowledge_document"
    assert KnowledgeChunk.__tablename__ == "knowledge_chunk"
    assert KnowledgeIndexJob.__tablename__ == "knowledge_index_job"
    assert "metadata" in KnowledgeDocument.__table__.c
    assert "metadata" in KnowledgeChunk.__table__.c


def _index_names(engine, table_name: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename=:table_name"
            ),
            {"table_name": table_name},
        ).fetchall()
    return {row[0] for row in rows}


@pytest.mark.anyio
async def test_knowledge_tables_upgrade_and_downgrade(_test_db_url):
    alembic_upgrade(_test_db_url, "head")
    engine = create_engine(to_sync_url(_test_db_url))
    try:
        doc_indexes = _index_names(engine, "knowledge_document")
        chunk_indexes = _index_names(engine, "knowledge_chunk")
        job_indexes = _index_names(engine, "knowledge_index_job")

        assert {
            "idx_knowledge_document_source",
            "idx_knowledge_document_product",
            "idx_knowledge_document_status_active",
        } <= doc_indexes
        assert {
            "idx_knowledge_chunk_document_index",
            "idx_knowledge_chunk_text_search",
            "idx_knowledge_chunk_embedding",
        } <= chunk_indexes
        assert {"idx_knowledge_index_job_status_priority"} <= job_indexes

        alembic_downgrade(_test_db_url, "0013_ai_permissions")
        with engine.connect() as conn:
            remaining = conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'knowledge_%'"
                )
            ).fetchall()
        assert remaining == []
    finally:
        engine.dispose()
