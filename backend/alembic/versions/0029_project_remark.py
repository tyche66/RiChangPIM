"""project_remark

补齐 ``projects.remark`` 列：CRM 的 ``Project`` 序列化与创建入参都带
``remark``（项目备注），但模型与迁移里一直没有这一列，导致
``POST /api/v1/projects`` 在 ``_project_to_dict`` 上直接 AttributeError。
本迁移只做纯增量（可空），旧数据无需回填。

Revision ID: 0029_project_remark
Revises: 0028_project_spaces
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_project_remark"
down_revision: Union[str, None] = "0028_project_spaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _inspector().get_columns(table))


def upgrade() -> None:
    if not _has_table("projects") or _has_column("projects", "remark"):
        return
    op.add_column("projects", sa.Column("remark", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_table("projects") and _has_column("projects", "remark"):
        op.drop_column("projects", "remark")
