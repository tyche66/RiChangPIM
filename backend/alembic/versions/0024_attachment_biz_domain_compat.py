"""attachment_biz_domain_compat

幂等兼容迁移：为 attachment 表添加 biz_domain 和 biz_scope_id 列。
背景：ORM 模型（app/models/product.py Attachment）已定义 biz_domain / biz_scope_id，
但迁移链从未添加过这两列。线上数据库执行产品列表 API 时，asyncpg 报
UndefinedColumnError: column attachment_1.biz_domain does not exist。
本迁移使用 IF NOT EXISTS 保证幂等性，可安全地在已有列的数据库上重复执行。

注意：本文件是生产运行镜像同名迁移（0024_attachment_biz_domain_compat）的重建版：
生产镜像的只读导出在文本管道中损坏（注释吞行导致 SyntaxError），SQL 语句按导出
原文逐字保留，仅修复注释与代码排版；revision/down_revision 与生产镜像一致。

Revision ID: 0024_attachment_biz_domain_compat
Revises: 0023_crm_sales_links_compat
Create Date: 2026-10-13
"""
from collections.abc import Sequence

from sqlalchemy.sql import text

from alembic import op

revision: str = "0024_attachment_biz_domain_compat"
down_revision: str | None = "0023_crm_sales_links_compat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 幂等添加 biz_domain 列（String(32)，nullable）
    # 使用 IF NOT EXISTS 避免在已有列的数据库上报错
    op.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'attachment' AND column_name = 'biz_domain'
                ) THEN
                    ALTER TABLE attachment ADD COLUMN biz_domain VARCHAR(32);
                END IF;
            END $$;
            """
        )
    )

    # 幂等添加 biz_scope_id 列（UUID，nullable）
    op.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'attachment' AND column_name = 'biz_scope_id'
                ) THEN
                    ALTER TABLE attachment ADD COLUMN biz_scope_id UUID;
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    # 降级时删除列（如果存在）
    op.execute(
        text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'attachment' AND column_name = 'biz_scope_id'
                ) THEN
                    ALTER TABLE attachment DROP COLUMN biz_scope_id;
                END IF;
            END $$;
            """
        )
    )

    op.execute(
        text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'attachment' AND column_name = 'biz_domain'
                ) THEN
                    ALTER TABLE attachment DROP COLUMN biz_domain;
                END IF;
            END $$;
            """
        )
    )
