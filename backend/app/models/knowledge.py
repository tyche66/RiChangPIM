from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from app.core.database import HalfVector
from app.models.base import CommonBase


class KnowledgeDocument(CommonBase):
    __tablename__ = "knowledge_document"

    source_type = Column(String(32), nullable=False)
    source_id = Column(PGUUID(as_uuid=True), nullable=True)
    product_id = Column(PGUUID(as_uuid=True), ForeignKey("product.id"), nullable=True)
    category_id = Column(PGUUID(as_uuid=True), ForeignKey("category.id"), nullable=True)
    brand_id = Column(PGUUID(as_uuid=True), ForeignKey("brand.id"), nullable=True)
    attachment_id = Column(PGUUID(as_uuid=True), ForeignKey("attachment.id"), nullable=True)
    title = Column(String(255), nullable=False)
    doc_type = Column(String(32), nullable=False)
    version = Column(String(64), nullable=True)
    language = Column(String(16), nullable=True)
    content_hash = Column(String(64), nullable=False)
    parse_status = Column(String(20), nullable=False, default="pending")
    index_status = Column(String(20), nullable=False, default="pending")
    is_active = Column(Boolean, nullable=False, default=True)
    visibility = Column(String(20), nullable=False, default="internal")
    required_permission = Column(String(64), nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)
    parser_name = Column(String(64), nullable=True)
    parser_version = Column(String(32), nullable=True)
    last_indexed_at = Column(DateTime(timezone=True), nullable=True)
    effective_at = Column(DateTime(timezone=True), nullable=True)
    expired_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "parse_status IN ('pending', 'processing', 'parsed', 'failed', 'ocr_required')",
            name="check_knowledge_document_parse_status",
        ),
        CheckConstraint(
            (
                "index_status IN ('pending', 'dispatched', 'processing', "
                "'indexed', 'failed', 'degraded')"
            ),
            name="check_knowledge_document_index_status",
        ),
        CheckConstraint(
            "visibility IN ('internal', 'restricted', 'private')",
            name="check_knowledge_document_visibility",
        ),
        Index("idx_knowledge_document_source", "source_type", "source_id"),
        Index("idx_knowledge_document_product", "product_id"),
        Index("idx_knowledge_document_category", "category_id"),
        Index("idx_knowledge_document_brand", "brand_id"),
        Index("idx_knowledge_document_status_active", "index_status", "is_active"),
    )

    product = relationship("Product")
    category = relationship("Category")
    brand = relationship("Brand")
    attachment = relationship("Attachment")
    chunks = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class KnowledgeChunk(CommonBase):
    __tablename__ = "knowledge_chunk"

    document_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_document.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(PGUUID(as_uuid=True), ForeignKey("product.id"), nullable=True)
    category_id = Column(PGUUID(as_uuid=True), ForeignKey("category.id"), nullable=True)
    brand_id = Column(PGUUID(as_uuid=True), ForeignKey("brand.id"), nullable=True)
    chunk_index = Column(Integer, nullable=False)
    section_path = Column(String(512), nullable=True)
    page_from = Column(Integer, nullable=True)
    page_to = Column(Integer, nullable=True)
    chunk_type = Column(String(32), nullable=False, default="text")
    chunk_text = Column(Text, nullable=False)
    normalized_text = Column(Text, nullable=True)
    text_search = Column(TSVECTOR, nullable=True)
    embedding = Column(HalfVector(2048), nullable=True)
    token_count = Column(Integer, nullable=True)
    embedding_model = Column(String(128), nullable=True)
    embedding_version = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=False)
    metadata_json = Column("metadata", JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint("chunk_index >= 0", name="check_knowledge_chunk_index_non_negative"),
        CheckConstraint(
            "page_from IS NULL OR page_from >= 1",
            name="check_knowledge_chunk_page_from",
        ),
        CheckConstraint(
            "page_to IS NULL OR page_to >= 1",
            name="check_knowledge_chunk_page_to",
        ),
        CheckConstraint(
            "page_from IS NULL OR page_to IS NULL OR page_from <= page_to",
            name="check_knowledge_chunk_page_range",
        ),
        Index(
            "idx_knowledge_chunk_document_index",
            "document_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("idx_knowledge_chunk_product", "product_id"),
        Index("idx_knowledge_chunk_category", "category_id"),
        Index("idx_knowledge_chunk_brand", "brand_id"),
        Index(
            "idx_knowledge_chunk_content_hash_active",
            "document_id",
            "content_hash",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    document = relationship("KnowledgeDocument", back_populates="chunks")
    product = relationship("Product")
    category = relationship("Category")
    brand = relationship("Brand")


class KnowledgeIndexJob(CommonBase):
    __tablename__ = "knowledge_index_job"

    source_type = Column(String(32), nullable=False)
    source_id = Column(PGUUID(as_uuid=True), nullable=True)
    operation = Column(String(16), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    content_hash = Column(String(64), nullable=True)
    pipeline_version = Column(String(32), nullable=True)
    priority = Column(Integer, nullable=False, default=100)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String(128), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    trace_id = Column(String(64), nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "operation IN ('upsert', 'delete', 'reindex')",
            name="check_knowledge_index_job_operation",
        ),
        CheckConstraint(
            "status IN ('pending', 'dispatched', 'processing', 'succeeded', 'failed', 'dead')",
            name="check_knowledge_index_job_status",
        ),
        CheckConstraint("priority >= 0", name="check_knowledge_index_job_priority"),
        CheckConstraint("attempt_count >= 0", name="check_knowledge_index_job_attempt_count"),
        CheckConstraint("max_attempts >= 1", name="check_knowledge_index_job_max_attempts"),
        Index("idx_knowledge_index_job_status_priority", "status", "priority", "next_attempt_at"),
        Index("idx_knowledge_index_job_source", "source_type", "source_id"),
    )

    creator = relationship("User")
