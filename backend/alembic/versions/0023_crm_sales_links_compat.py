"""add CRM links to legacy proposal rows

The v1.9.3 source model added nullable customer/project links to the legacy
proposal table, but the cloud package omitted the corresponding migration.
This forward-only compatibility migration adds those columns and indexes.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0023_crm_sales_links_compat"
down_revision: str | None = "0022_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE proposal ADD COLUMN IF NOT EXISTS customer_id UUID")
    op.execute("ALTER TABLE proposal ADD COLUMN IF NOT EXISTS project_id UUID")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'proposal_customer_id_fkey'
            ) THEN
                ALTER TABLE proposal
                    ADD CONSTRAINT proposal_customer_id_fkey
                    FOREIGN KEY (customer_id) REFERENCES customers(id);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'proposal_project_id_fkey'
            ) THEN
                ALTER TABLE proposal
                    ADD CONSTRAINT proposal_project_id_fkey
                    FOREIGN KEY (project_id) REFERENCES projects(id);
            END IF;
        END
        $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_proposal_customer_id ON proposal(customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_proposal_project_id ON proposal(project_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_proposal_project_id")
    op.execute("DROP INDEX IF EXISTS ix_proposal_customer_id")
    op.execute("ALTER TABLE proposal DROP CONSTRAINT IF EXISTS proposal_project_id_fkey")
    op.execute("ALTER TABLE proposal DROP CONSTRAINT IF EXISTS proposal_customer_id_fkey")
    op.execute("ALTER TABLE proposal DROP COLUMN IF EXISTS project_id")
    op.execute("ALTER TABLE proposal DROP COLUMN IF EXISTS customer_id")