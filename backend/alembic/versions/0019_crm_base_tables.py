"""crm base tables compatibility bridge

The v1.9.3 package references customers/projects from the content migration,
but the package snapshot omitted the CRM base-table migrations. The target
already has the target-local 0018 migration, so create the two referenced base
tables before 0020/0021. The remaining CRM tables are created idempotently by
Base.metadata.create_all during the normal startup entrypoint.
"""
from collections.abc import Sequence

from alembic import op

from app.models.customer import Customer
from app.models.project import Project

revision: str = "0019_crm_base_tables"
down_revision: str | None = "0018_qwen_embedding_hnsw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Customer.__table__.create(bind=bind, checkfirst=True)
    Project.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Project.__table__.drop(bind=bind, checkfirst=True)
    Customer.__table__.drop(bind=bind, checkfirst=True)