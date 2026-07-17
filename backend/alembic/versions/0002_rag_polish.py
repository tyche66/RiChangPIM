"""rag_polish

Revision ID: 0002_rag_polish
Revises: 0001_initial
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '0002_rag_polish'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('product_manual_chunk',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_manual_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('chunk_text', sa.Text, nullable=False),
        sa.Column('chunk_tokens', sa.Integer, nullable=True),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['product_manual_id'], ['product_manual.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['product.id'], ondelete='CASCADE'),
    )

    op.execute("""
        CREATE INDEX idx_product_manual_chunk_embedding
        ON product_manual_chunk USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
    """)

    op.create_index('idx_product_manual_chunk_manual', 'product_manual_chunk', ['product_manual_id'])
    op.create_index('idx_product_manual_chunk_product', 'product_manual_chunk', ['product_id'])

    op.execute("""
        CREATE TRIGGER update_product_manual_chunk_updated_at
        BEFORE UPDATE ON product_manual_chunk
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.add_column('proposal', sa.Column('ai_polish_content', sa.Text, nullable=True))
    op.add_column('proposal', sa.Column('ai_polish_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('proposal', sa.Column('ai_polish_model', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('proposal', 'ai_polish_model')
    op.drop_column('proposal', 'ai_polish_at')
    op.drop_column('proposal', 'ai_polish_content')

    op.execute('DROP TRIGGER IF EXISTS update_product_manual_chunk_updated_at ON product_manual_chunk')

    op.drop_index('idx_product_manual_chunk_product', table_name='product_manual_chunk')
    op.drop_index('idx_product_manual_chunk_manual', table_name='product_manual_chunk')
    op.execute('DROP INDEX IF EXISTS idx_product_manual_chunk_embedding')

    op.drop_table('product_manual_chunk')
