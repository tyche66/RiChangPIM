"""knowledge_tables

Revision ID: 0014_knowledge_tables
Revises: 0013_ai_permissions
Create Date: 2026-07-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0014_knowledge_tables"
down_revision: Union[str, None] = "0013_ai_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    op.create_table(
        "knowledge_document",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("parse_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("index_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="internal"),
        sa.Column("required_permission", sa.String(length=64), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parser_name", sa.String(length=64), nullable=True),
        sa.Column("parser_version", sa.String(length=32), nullable=True),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachment.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brand.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.CheckConstraint(
            "parse_status IN ('pending', 'processing', 'parsed', 'failed', 'ocr_required')",
            name="check_knowledge_document_parse_status",
        ),
        sa.CheckConstraint(
            "index_status IN ('pending', 'dispatched', 'processing', 'indexed', 'failed', 'degraded')",
            name="check_knowledge_document_index_status",
        ),
        sa.CheckConstraint(
            "visibility IN ('internal', 'restricted', 'private')",
            name="check_knowledge_document_visibility",
        ),
    )

    op.create_table(
        "knowledge_chunk",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.String(length=512), nullable=True),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.Column("chunk_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("text_search", postgresql.TSVECTOR(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("embedding_version", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["brand_id"], ["brand.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.CheckConstraint("chunk_index >= 0", name="check_knowledge_chunk_index_non_negative"),
        sa.CheckConstraint("page_from IS NULL OR page_from >= 1", name="check_knowledge_chunk_page_from"),
        sa.CheckConstraint("page_to IS NULL OR page_to >= 1", name="check_knowledge_chunk_page_to"),
        sa.CheckConstraint(
            "page_from IS NULL OR page_to IS NULL OR page_from <= page_to",
            name="check_knowledge_chunk_page_range",
        ),
    )

    op.create_table(
        "knowledge_index_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("pipeline_version", sa.String(length=32), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.CheckConstraint(
            "operation IN ('upsert', 'delete', 'reindex')",
            name="check_knowledge_index_job_operation",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'dispatched', 'processing', 'succeeded', 'failed', 'dead')",
            name="check_knowledge_index_job_status",
        ),
        sa.CheckConstraint("priority >= 0", name="check_knowledge_index_job_priority"),
        sa.CheckConstraint("attempt_count >= 0", name="check_knowledge_index_job_attempt_count"),
        sa.CheckConstraint("max_attempts >= 1", name="check_knowledge_index_job_max_attempts"),
    )

    op.create_index("idx_knowledge_document_source", "knowledge_document", ["source_type", "source_id"])
    op.create_index("idx_knowledge_document_product", "knowledge_document", ["product_id"])
    op.create_index("idx_knowledge_document_category", "knowledge_document", ["category_id"])
    op.create_index("idx_knowledge_document_brand", "knowledge_document", ["brand_id"])
    op.create_index(
        "idx_knowledge_document_status_active",
        "knowledge_document",
        ["index_status", "is_active"],
    )

    op.create_index(
        "idx_knowledge_chunk_document_index",
        "knowledge_chunk",
        ["document_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index("idx_knowledge_chunk_product", "knowledge_chunk", ["product_id"])
    op.create_index("idx_knowledge_chunk_category", "knowledge_chunk", ["category_id"])
    op.create_index("idx_knowledge_chunk_brand", "knowledge_chunk", ["brand_id"])
    op.create_index(
        "idx_knowledge_chunk_content_hash_active",
        "knowledge_chunk",
        ["document_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.execute(
        """
        CREATE INDEX idx_knowledge_chunk_text_search
        ON knowledge_chunk USING gin (text_search)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_knowledge_chunk_embedding
        ON knowledge_chunk USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
        """
    )

    op.create_index(
        "idx_knowledge_index_job_status_priority",
        "knowledge_index_job",
        ["status", "priority", "next_attempt_at"],
    )
    op.create_index("idx_knowledge_index_job_source", "knowledge_index_job", ["source_type", "source_id"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_knowledge_chunk_text_search()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.text_search := to_tsvector(
                'simple',
                coalesce(NEW.normalized_text, NEW.chunk_text, '')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_knowledge_document_updated_at
        BEFORE UPDATE ON knowledge_document
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_knowledge_chunk_updated_at
        BEFORE UPDATE ON knowledge_chunk
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_knowledge_index_job_updated_at
        BEFORE UPDATE ON knowledge_index_job
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_knowledge_chunk_text_search
        BEFORE INSERT OR UPDATE OF chunk_text, normalized_text ON knowledge_chunk
        FOR EACH ROW EXECUTE FUNCTION update_knowledge_chunk_text_search()
        """
    )

    op.execute(
        """
        UPDATE knowledge_chunk
        SET text_search = to_tsvector('simple', coalesce(normalized_text, chunk_text, ''))
        WHERE text_search IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_knowledge_chunk_text_search ON knowledge_chunk")
    op.execute("DROP TRIGGER IF EXISTS update_knowledge_index_job_updated_at ON knowledge_index_job")
    op.execute("DROP TRIGGER IF EXISTS update_knowledge_chunk_updated_at ON knowledge_chunk")
    op.execute("DROP TRIGGER IF EXISTS update_knowledge_document_updated_at ON knowledge_document")
    op.execute("DROP FUNCTION IF EXISTS update_knowledge_chunk_text_search()")

    op.drop_index("idx_knowledge_index_job_source", table_name="knowledge_index_job")
    op.drop_index("idx_knowledge_index_job_status_priority", table_name="knowledge_index_job")

    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunk_embedding")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunk_text_search")
    op.drop_index("idx_knowledge_chunk_content_hash_active", table_name="knowledge_chunk")
    op.drop_index("idx_knowledge_chunk_brand", table_name="knowledge_chunk")
    op.drop_index("idx_knowledge_chunk_category", table_name="knowledge_chunk")
    op.drop_index("idx_knowledge_chunk_product", table_name="knowledge_chunk")
    op.drop_index("idx_knowledge_chunk_document_index", table_name="knowledge_chunk")

    op.drop_index("idx_knowledge_document_status_active", table_name="knowledge_document")
    op.drop_index("idx_knowledge_document_brand", table_name="knowledge_document")
    op.drop_index("idx_knowledge_document_category", table_name="knowledge_document")
    op.drop_index("idx_knowledge_document_product", table_name="knowledge_document")
    op.drop_index("idx_knowledge_document_source", table_name="knowledge_document")

    op.drop_table("knowledge_index_job")
    op.drop_table("knowledge_chunk")
    op.drop_table("knowledge_document")
