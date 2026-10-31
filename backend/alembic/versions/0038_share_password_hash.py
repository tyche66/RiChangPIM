"""share_token password hash

Revision ID: 0038_share_password_hash
Revises: 0037_knowledge_index_scheduler
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import bcrypt
import sqlalchemy as sa

from alembic import op

revision: str = "0038_share_password_hash"
down_revision: str | None = "0037_knowledge_index_scheduler"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "share_token",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, password FROM share_token "
            "WHERE password IS NOT NULL AND password <> ''"
        )
    ).fetchall()
    for row in rows:
        stored = str(row.password)
        if stored.startswith(("$2a$", "$2b$", "$2y$")):
            hashed = stored
        else:
            raw = stored.encode("utf-8")[:72]
            hashed = bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")
        # Keep the hash in both columns so rolling back to the old code locks
        # password-protected shares instead of silently making them passwordless.
        conn.execute(
            sa.text(
                "UPDATE share_token SET password_hash = :hashed, password = :hashed "
                "WHERE id = :id"
            ),
            {"hashed": hashed, "id": row.id},
        )


def downgrade() -> None:
    op.drop_column("share_token", "password_hash")
