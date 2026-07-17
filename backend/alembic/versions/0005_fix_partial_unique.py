"""fix_partial_unique

补全 P1.2「UNIQUE 软删除语义统一」的迁移升级路径。

背景：P1.2 修复时只改了历史 ``0001_initial``（对 ``product.product_no`` 与
``share_token.token`` 移除普通 UNIQUE、仅保留 ``WHERE is_deleted = false`` 的
partial 唯一）。这对**全新数据库**正确，但对**已经执行过旧 0001** 的数据库，
``alembic upgrade head`` 不会删除原普通 UNIQUE 约束
（``product_product_no_key`` / ``share_token_token_key``），导致软删除后无法复用
编号/令牌，与 partial 语义矛盾，且理论上升级后的 schema 与新建库不一致。

本修订在「已存在旧约束」的库上删除普通 UNIQUE，仅保留 partial UNIQUE，
使旧库与新库收敛到同一 schema；对新库（约束本就不存在）为 no-op。

幂等：使用 ``DROP CONSTRAINT IF EXISTS``，重复执行安全。

Revision ID: 0005_fix_partial_unique
Revises: 0004_seed_data
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_fix_partial_unique"
down_revision: Union[str, None] = "0004_seed_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 旧版 0001 在 P1.2 之前对 product_no / share_token.token 建了
    # 普通 UNIQUE + partial UNIQUE；此处移除普通 UNIQUE，仅留 partial。
    op.execute('ALTER TABLE product DROP CONSTRAINT IF EXISTS product_product_no_key')
    op.execute('ALTER TABLE share_token DROP CONSTRAINT IF EXISTS share_token_token_key')


def downgrade() -> None:
    # 回滚到「普通 UNIQUE 仍存在」的状态（与升级前一致，partial 唯一仍保留）。
    op.create_unique_constraint('product_product_no_key', 'product', ['product_no'])
    op.create_unique_constraint('share_token_token_key', 'share_token', ['token'])
