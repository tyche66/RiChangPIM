"""qwen_embedding_hnsw

Keep the model-aligned HNSW index for the active product-card embedding space
under Alembic control. The online deployment may already have created it, so
the upgrade is intentionally idempotent.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_qwen_embedding_hnsw"
down_revision: str | None = "0017_operation_log_username"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_embedding_qwen
        ON knowledge_chunk USING hnsw (embedding halfvec_cosine_ops)
        WHERE embedding IS NOT NULL
          AND embedding_model = 'Qwen3-Embedding-8B'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunk_embedding_qwen")