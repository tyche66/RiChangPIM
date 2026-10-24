"""content DNA provenance and verification fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0027_content_dna_fields"
down_revision: str | None = "0026_project_remark"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_column(table: str, column: str) -> bool:
    return any(item["name"] == column for item in _inspector().get_columns(table))


def _add(table: str, column: sa.Column) -> None:
    if _has_table(table) and not _has_column(table, column.name):
        op.add_column(table, column)


def upgrade() -> None:
    _add("content_skills", sa.Column("source_dna", sa.String(32), nullable=True))
    _add("content_topic_items", sa.Column("pillar_code", sa.String(1), nullable=True))
    _add(
        "content_topic_items",
        sa.Column(
            "verification_gaps",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    _add(
        "content_items",
        sa.Column(
            "verification_gaps",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    if _has_table("content_items") and _has_column("content_items", "verification_gaps"):
        op.drop_column("content_items", "verification_gaps")
    if _has_table("content_topic_items") and _has_column(
        "content_topic_items", "verification_gaps"
    ):
        op.drop_column("content_topic_items", "verification_gaps")
    if _has_table("content_topic_items") and _has_column("content_topic_items", "pillar_code"):
        op.drop_column("content_topic_items", "pillar_code")
    if _has_table("content_skills") and _has_column("content_skills", "source_dna"):
        op.drop_column("content_skills", "source_dna")
