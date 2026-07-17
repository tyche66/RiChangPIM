"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.update_time = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.create_table('role',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_name', sa.String(length=64), nullable=False),
        sa.Column('role_code', sa.String(length=32), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role_code')
    )

    op.create_table('permission',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('perm_code', sa.String(length=64), nullable=False),
        sa.Column('perm_name', sa.String(length=64), nullable=False),
        sa.Column('resource', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('perm_code')
    )

    op.create_table('role_permission',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('permission_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['permission_id'], ['permission.id'], ),
        sa.ForeignKeyConstraint(['role_id'], ['role.id'], )
    )

    op.create_table('user',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=128), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, default='active'),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('last_login_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['role_id'], ['role.id'], ),
        sa.UniqueConstraint('username')
    )

    op.create_table('category',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('level', sa.Integer, nullable=False),
        sa.Column('category_name', sa.String(length=128), nullable=False),
        sa.Column('sort', sa.Integer, nullable=False, default=0),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['parent_id'], ['category.id'], )
    )

    op.create_table('brand',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('brand_name', sa.String(length=128), nullable=False),
        sa.Column('logo_url', sa.String(length=512), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('brand_name')
    )

    op.create_table('supplier',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('supplier_name', sa.String(length=128), nullable=False),
        sa.Column('contact', sa.String(length=64), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('cooperation_status', sa.String(length=20), nullable=False, default='active'),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier_name'),
        sa.CheckConstraint("cooperation_status IN ('active', 'suspended', 'terminated')", name='check_supplier_cooperation_status')
    )

    op.create_table('tag',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tag_name', sa.String(length=64), nullable=False),
        sa.Column('tag_type', sa.String(length=32), nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('attachment',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_url', sa.String(length=512), nullable=False),
        sa.Column('file_type', sa.String(length=32), nullable=False),
        sa.Column('file_size', sa.Integer, nullable=False),
        sa.Column('storage_type', sa.String(length=20), nullable=False, default='minio'),
        sa.Column('oss_key', sa.String(length=512), nullable=False),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("file_type IN ('image', 'video', 'pdf', 'doc', 'other')", name='check_attachment_file_type')
    )

    op.create_table('product',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_no', sa.String(length=64), nullable=False),
        sa.Column('product_name', sa.String(length=255), nullable=False),
        sa.Column('brand_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('supplier_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('face_price', sa.Float, nullable=False),
        sa.Column('cost_price', sa.Float, nullable=True),
        sa.Column('material', sa.String(length=128), nullable=True),
        sa.Column('stock_status', sa.String(length=20), nullable=False, default='in_stock'),
        sa.Column('status', sa.String(length=20), nullable=False, default='draft'),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('vector', Vector(1536), nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['brand_id'], ['brand.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['category.id'], ),
        sa.ForeignKeyConstraint(['supplier_id'], ['supplier.id'], ),
        sa.CheckConstraint("status IN ('active', 'inactive', 'draft')", name='check_product_status'),
        sa.CheckConstraint("stock_status IN ('in_stock', 'out_of_stock', 'preorder')", name='check_product_stock_status'),
    )

    op.create_table('product_tag',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tag_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['product_id'], ['product.id', ], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tag.id'], )
    )

    op.create_table('product_image',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('attachment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sort', sa.Integer, nullable=False, default=0),
        sa.Column('is_cover', sa.Boolean, nullable=False, default=False),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['attachment_id'], ['attachment.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['product.id'], )
    )

    op.create_table('product_manual',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('attachment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('doc_type', sa.String(length=32), nullable=False),
        sa.Column('parsed_content', sa.Text, nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['attachment_id'], ['attachment.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['product.id'], ),
        sa.CheckConstraint("doc_type IN ('manual', 'spec', 'datasheet', 'certificate', 'other')", name='check_product_manual_doc_type')
    )

    op.create_table('proposal',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('proposal_no', sa.String(length=64), nullable=False),
        sa.Column('proposal_name', sa.String(length=255), nullable=False),
        sa.Column('creator_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_name', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, default='draft'),
        sa.Column('ai_polished', sa.Boolean, nullable=False, default=False),
        sa.Column('total_face_value', sa.Float, nullable=False, default=0),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['creator_id'], ['user.id'], ),
        sa.UniqueConstraint('proposal_no')
    )

    op.create_table('quotation',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('quotation_no', sa.String(length=64), nullable=False),
        sa.Column('proposal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('creator_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_amount', sa.Float, nullable=False, default=0),
        sa.Column('tax_rate', sa.Float, nullable=False, default=0.13),
        sa.Column('discount', sa.Float, nullable=False, default=1.0),
        sa.Column('status', sa.String(length=20), nullable=False, default='draft'),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['creator_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['proposal_id'], ['proposal.id'], ),
        sa.UniqueConstraint('quotation_no')
    )

    op.create_table('proposal_item',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('proposal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False, default=1),
        sa.Column('sort', sa.Integer, nullable=False, default=0),
        sa.Column('remark', sa.Text, nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['product_id'], ['product.id'], ),
        sa.ForeignKeyConstraint(['proposal_id'], ['proposal.id', ], ondelete='CASCADE')
    )

    op.create_table('quotation_item',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('quotation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False, default=1),
        sa.Column('unit_price', sa.Float, nullable=False),
        sa.Column('tax_rate', sa.Float, nullable=False, default=0.13),
        sa.Column('subtotal', sa.Float, nullable=False),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['product_id'], ['product.id'], ),
        sa.ForeignKeyConstraint(['quotation_id'], ['quotation.id', ], ondelete='CASCADE')
    )

    op.create_table('share',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('share_type', sa.String(length=20), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('creator_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, default='active'),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['creator_id'], ['user.id'], )
    )

    op.create_table('share_token',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('share_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=True),
        sa.Column('expire_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('max_access_count', sa.Integer, nullable=True),
        sa.Column('current_access_count', sa.Integer, nullable=False, default=0),
        sa.Column('status', sa.String(length=20), nullable=False, default='active'),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['share_id'], ['share.id'], ),
    )

    # visitor 必须在 share_log 之前创建：share_log.visitor_id 外键引用 visitor.id。
    op.create_table('visitor',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('fingerprint', sa.String(length=128), nullable=True),
        sa.Column('openid', sa.String(length=64), nullable=True),
        sa.Column('unionid', sa.String(length=64), nullable=True),
        sa.Column('nickname', sa.String(length=128), nullable=True),
        sa.Column('avatar_url', sa.String(length=512), nullable=True),
        sa.Column('first_seen_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_seen_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('openid')
    )

    op.create_table('share_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('share_token_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('visitor_ip', sa.String(length=64), nullable=True),
        sa.Column('visitor_ua', sa.String(length=512), nullable=True),
        sa.Column('device_fingerprint', sa.String(length=128), nullable=True),
        sa.Column('openid', sa.String(length=64), nullable=True),
        sa.Column('access_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('access_result', sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['share_token_id'], ['share_token.id'], ),
        sa.ForeignKeyConstraint(['visitor_id'], ['visitor.id'], )
    )

    op.create_table('operation_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('module', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('request_body', sa.Text, nullable=True),
        sa.Column('response_code', sa.Integer, nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('operate_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], )
    )

    op.create_table('ai_conversation',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('question', sa.Text, nullable=False),
        sa.Column('answer', sa.Text, nullable=True),
        sa.Column('sources', sa.Text, nullable=True),
        sa.Column('tool_calls', sa.Text, nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], )
    )

    for tbl in ['role', 'permission', 'role_permission', 'user', 'category', 'brand', 'supplier', 'tag',
                'attachment', 'product', 'product_tag', 'product_image', 'product_manual',
                'proposal', 'proposal_item', 'quotation', 'quotation_item',
                'share', 'share_token', 'visitor']:
        op.execute(f"""
            CREATE TRIGGER update_{tbl}_updated_at
            BEFORE UPDATE ON "{tbl}"
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)

    op.create_index('idx_role_code_active', 'role', ['role_code'], unique=True, postgresql_where=sa.text("is_deleted = false"))
    op.create_index('idx_perm_code_active', 'permission', ['perm_code'], unique=True, postgresql_where=sa.text("is_deleted = false"))
    op.create_index('idx_product_no_active', 'product', ['product_no'], unique=True, postgresql_where=sa.text("is_deleted = false"))
    op.create_index('idx_product_category', 'product', ['category_id'])
    op.create_index('idx_product_brand', 'product', ['brand_id'])
    op.create_index('idx_product_status', 'product', ['status'])
    op.create_index('idx_product_stock_status', 'product', ['stock_status'])
    op.create_index('idx_proposal_creator', 'proposal', ['creator_id'])
    op.create_index('idx_quotation_proposal', 'quotation', ['proposal_id'])
    op.create_index('idx_share_token_token', 'share_token', ['token'], unique=True, postgresql_where=sa.text("is_deleted = false"))
    op.create_index('idx_share_token_share', 'share_token', ['share_id'])
    op.create_index('idx_operation_log_user', 'operation_log', ['user_id'])
    op.create_index('idx_operation_log_module', 'operation_log', ['module'])

    op.execute("""
        CREATE INDEX idx_product_vector ON product USING hnsw (vector vector_cosine_ops)
        WHERE vector IS NOT NULL
    """)


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS update_visitor_updated_at ON visitor')
    op.execute('DROP TRIGGER IF EXISTS update_share_token_updated_at ON share_token')
    op.execute('DROP TRIGGER IF EXISTS update_share_updated_at ON share')
    op.execute('DROP TRIGGER IF EXISTS update_quotation_item_updated_at ON quotation_item')
    op.execute('DROP TRIGGER IF EXISTS update_quotation_updated_at ON quotation')
    op.execute('DROP TRIGGER IF EXISTS update_proposal_item_updated_at ON proposal_item')
    op.execute('DROP TRIGGER IF EXISTS update_proposal_updated_at ON proposal')
    op.execute('DROP TRIGGER IF EXISTS update_product_manual_updated_at ON product_manual')
    op.execute('DROP TRIGGER IF EXISTS update_product_image_updated_at ON product_image')
    op.execute('DROP TRIGGER IF EXISTS update_product_tag_updated_at ON product_tag')
    op.execute('DROP TRIGGER IF EXISTS update_product_updated_at ON product')
    op.execute('DROP TRIGGER IF EXISTS update_attachment_updated_at ON attachment')
    op.execute('DROP TRIGGER IF EXISTS update_tag_updated_at ON tag')
    op.execute('DROP TRIGGER IF EXISTS update_supplier_updated_at ON supplier')
    op.execute('DROP TRIGGER IF EXISTS update_brand_updated_at ON brand')
    op.execute('DROP TRIGGER IF EXISTS update_category_updated_at ON category')
    op.execute('DROP TRIGGER IF EXISTS update_user_updated_at ON "user"')
    op.execute('DROP TRIGGER IF EXISTS update_role_permission_updated_at ON role_permission')
    op.execute('DROP TRIGGER IF EXISTS update_permission_updated_at ON permission')
    op.execute('DROP TRIGGER IF EXISTS update_role_updated_at ON role')
    op.execute('DROP FUNCTION IF EXISTS update_updated_at_column')

    # Drop children before parents (reverse of creation order) to satisfy FKs.
    op.drop_table('ai_conversation')
    op.drop_table('operation_log')
    op.drop_table('share_log')
    op.drop_table('visitor')
    op.drop_table('share_token')
    op.drop_table('share')
    op.drop_table('quotation_item')
    op.drop_table('proposal_item')
    op.drop_table('quotation')
    op.drop_table('proposal')
    op.drop_table('product_manual')
    op.drop_table('product_image')
    op.drop_table('product_tag')
    op.drop_table('product')
    op.drop_table('attachment')
    op.drop_table('tag')
    op.drop_table('supplier')
    op.drop_table('brand')
    op.drop_table('category')
    op.drop_table('user')
    op.drop_table('role_permission')
    op.drop_table('permission')
    op.drop_table('role')
