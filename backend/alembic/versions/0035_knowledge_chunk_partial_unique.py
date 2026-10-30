"""knowledge_chunk 部分唯一索引

软删除会保留旧 chunk 行，而原全局唯一索引 (document_id, chunk_index) 仍把
这些历史行算进唯一性；内容变化后的重建在插入新版本时必然冲突，索引任务
因此反复重算 embedding。改为只约束未删除行后，同一位置允许“历史软删除行
+ 当前行”共存。

Revision ID: 0035_knowledge_chunk_partial_unique
Revises: 0034_user_token_version
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_knowledge_chunk_partial_unique"
down_revision: str | None = "0034_user_token_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "idx_knowledge_chunk_document_index"


def upgrade() -> None:
    # 线上可能已手工替换过该索引，先删后建保证升级幂等。
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    op.create_index(
        INDEX_NAME,
        "knowledge_chunk",
        ["document_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    # 恢复旧的全局唯一索引；若库中已有同位的软删除历史行，这里会失败并
    # 整体回滚，而不是删除审计数据。
    op.create_index(
        INDEX_NAME,
        "knowledge_chunk",
        ["document_id", "chunk_index"],
        unique=True,
    )
