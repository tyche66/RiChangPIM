"""embedding_dim_2048

Revision ID: 0016_embedding_dim_2048
Revises: 0015_pending_actions
Create Date: 2026-07-26 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_embedding_dim_2048"
down_revision: str | None = "0015_pending_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_product_vector")
    op.execute("DROP INDEX IF EXISTS idx_product_manual_chunk_embedding")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunk_embedding")
    op.execute("ALTER TABLE product ALTER COLUMN vector TYPE halfvec(2048) USING NULL")
    op.execute(
        "ALTER TABLE product_manual_chunk ALTER COLUMN embedding TYPE halfvec(2048) USING NULL"
    )
    op.execute("ALTER TABLE knowledge_chunk ALTER COLUMN embedding TYPE halfvec(2048) USING NULL")
    op.execute(
        """
        CREATE INDEX idx_product_vector
        ON product USING hnsw (vector halfvec_cosine_ops)
        WHERE vector IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_product_manual_chunk_embedding
        ON product_manual_chunk USING hnsw (embedding halfvec_cosine_ops)
        WHERE embedding IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_knowledge_chunk_embedding
        ON knowledge_chunk USING hnsw (embedding halfvec_cosine_ops)
        WHERE embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_product_vector")
    op.execute("DROP INDEX IF EXISTS idx_product_manual_chunk_embedding")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunk_embedding")
    op.execute("ALTER TABLE knowledge_chunk ALTER COLUMN embedding TYPE vector(1536) USING NULL")
    op.execute(
        "ALTER TABLE product_manual_chunk ALTER COLUMN embedding TYPE vector(1536) USING NULL"
    )
    op.execute("ALTER TABLE product ALTER COLUMN vector TYPE vector(1536) USING NULL")
    op.execute(
        """
        CREATE INDEX idx_product_vector
        ON product USING hnsw (vector vector_cosine_ops)
        WHERE vector IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_product_manual_chunk_embedding
        ON product_manual_chunk USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_knowledge_chunk_embedding
        ON knowledge_chunk USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
        """
    )
