"""add_manual_indexing_and_conversation_fields

Revision ID: 0006_add_manual_indexing
Revises: 0005_fix_partial_unique
Create Date: 2026-07-16 12:00:00.000000

Adds RAG indexing state tracking to product_manual, idempotent chunk
uniqueness to product_manual_chunk, and AI conversation enrichment fields
(model, token_usage, status, summaries) so a separate worker can consume them.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_add_manual_indexing"
down_revision: Union[str, None] = "0005_fix_partial_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- product_manual: indexing state ---
    op.add_column(
        "product_manual",
        sa.Column(
            "index_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "product_manual",
        sa.Column("index_error", sa.Text, nullable=True),
    )
    op.add_column(
        "product_manual",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "product_manual",
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "check_product_manual_index_status",
        "product_manual",
        "index_status IN ('pending', 'processing', 'indexed', 'failed')",
    )

    # --- product_manual_chunk: idempotent uniqueness + hash ---
    op.add_column(
        "product_manual_chunk",
        sa.Column("chunk_hash", sa.String(64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_chunk_manual_index",
        "product_manual_chunk",
        ["product_manual_id", "chunk_index"],
    )

    # --- ai_conversation: enrichment fields for worker consumption ---
    # Use batch mode on the existing table; columns are nullable so ADD COLUMN
    # is safe on a populated table.
    op.add_column("ai_conversation", sa.Column("model", sa.String(64), nullable=True))
    op.add_column("ai_conversation", sa.Column("token_usage", sa.Text, nullable=True))
    op.add_column(
        "ai_conversation",
        sa.Column("status", sa.String(20), nullable=True, server_default="completed"),
    )
    op.add_column("ai_conversation", sa.Column("request_summary", sa.Text, nullable=True))
    op.add_column("ai_conversation", sa.Column("response_summary", sa.Text, nullable=True))


def downgrade() -> None:
    # ai_conversation
    op.drop_column("ai_conversation", "response_summary")
    op.drop_column("ai_conversation", "request_summary")
    op.drop_column("ai_conversation", "status")
    op.drop_column("ai_conversation", "token_usage")
    op.drop_column("ai_conversation", "model")

    # product_manual_chunk
    op.drop_constraint("uq_chunk_manual_index", "product_manual_chunk", type_="unique")
    op.drop_column("product_manual_chunk", "chunk_hash")

    # product_manual
    op.drop_constraint("check_product_manual_index_status", "product_manual", type_="check")
    op.drop_column("product_manual", "last_indexed_at")
    op.drop_column("product_manual", "content_hash")
    op.drop_column("product_manual", "index_error")
    op.drop_column("product_manual", "index_status")
