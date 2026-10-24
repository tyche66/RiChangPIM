"""add proposal customer/project columns and attachment biz columns

Revision ID: 0018_crm_core
Revises: 0017_operation_log_username
Create Date: 2026-10-14 00:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0018_crm_core'
down_revision = '0017_operation_log_username'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())

    # Add customer_id and project_id to proposal
    proposal_columns = {column['name'] for column in inspector.get_columns('proposal')}
    if 'customer_id' not in proposal_columns:
        op.add_column('proposal', sa.Column('customer_id', sa.UUID(), nullable=True))
    if 'project_id' not in proposal_columns:
        op.add_column('proposal', sa.Column('project_id', sa.UUID(), nullable=True))
    proposal_indexes = {index['name'] for index in inspector.get_indexes('proposal')}
    if 'ix_proposal_customer' not in proposal_indexes:
        op.create_index('ix_proposal_customer', 'proposal', ['customer_id'], unique=False)
    if 'ix_proposal_project' not in proposal_indexes:
        op.create_index('ix_proposal_project', 'proposal', ['project_id'], unique=False)
    
    # Add biz_domain and biz_scope_id to attachment
    attachment_columns = {column['name'] for column in inspector.get_columns('attachment')}
    if 'biz_domain' not in attachment_columns:
        op.add_column('attachment', sa.Column('biz_domain', sa.String(length=32), nullable=True))
    if 'biz_scope_id' not in attachment_columns:
        op.add_column('attachment', sa.Column('biz_scope_id', sa.UUID(), nullable=True))
    attachment_indexes = {index['name'] for index in inspector.get_indexes('attachment')}
    if 'ix_attachment_biz' not in attachment_indexes:
        op.create_index(
            'ix_attachment_biz', 'attachment', ['biz_domain', 'biz_scope_id'], unique=False
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    attachment_columns = {column['name'] for column in inspector.get_columns('attachment')}
    attachment_indexes = {index['name'] for index in inspector.get_indexes('attachment')}
    if 'ix_attachment_biz' in attachment_indexes:
        op.drop_index('ix_attachment_biz', table_name='attachment')
    if 'biz_scope_id' in attachment_columns:
        op.drop_column('attachment', 'biz_scope_id')
    if 'biz_domain' in attachment_columns:
        op.drop_column('attachment', 'biz_domain')
    
    proposal_columns = {column['name'] for column in inspector.get_columns('proposal')}
    proposal_indexes = {index['name'] for index in inspector.get_indexes('proposal')}
    if 'ix_proposal_project' in proposal_indexes:
        op.drop_index('ix_proposal_project', table_name='proposal')
    if 'ix_proposal_customer' in proposal_indexes:
        op.drop_index('ix_proposal_customer', table_name='proposal')
    if 'project_id' in proposal_columns:
        op.drop_column('proposal', 'project_id')
    if 'customer_id' in proposal_columns:
        op.drop_column('proposal', 'customer_id')
