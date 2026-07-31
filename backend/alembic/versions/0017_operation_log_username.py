"""operation_log_username

给 ``operation_log`` 增加操作人用户名快照。

为什么存快照而不是每次 join ``user``：
- 审计记录是历史事实，用户改名或被删除之后，日志仍应显示当时的操作人；
- 列表页高频翻页，少一次 join 也更省。

存量数据用当前 ``user.username`` 回填一次，回填不到（用户已被物理删除）就留空，
前端退化为显示用户编号，不编造。

Revision ID: 0017_operation_log_username
Revises: 0016_embedding_dim_2048
Create Date: 2026-07-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_operation_log_username"
down_revision: str | None = "0016_embedding_dim_2048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("operation_log", sa.Column("username", sa.String(64), nullable=True))
    op.execute(
        """
        UPDATE operation_log AS l
        SET username = u.username
        FROM "user" AS u
        WHERE l.user_id = u.id AND l.username IS NULL
        """
    )
    op.create_index("idx_operation_log_username", "operation_log", ["username"])


def downgrade() -> None:
    op.drop_index("idx_operation_log_username", table_name="operation_log")
    op.drop_column("operation_log", "username")
