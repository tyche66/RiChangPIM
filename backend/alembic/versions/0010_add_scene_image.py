"""add_scene_image

Revision ID: 0010_add_scene_image
Revises: 0009_sunon_pilot_product_fields
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_add_scene_image"
down_revision: str | None = "0009_sunon_pilot_product_fields"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "scene_image",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort", sa.Integer, nullable=False, default=0),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachment.id"]),
    )

    op.create_table(
        "product_scene_image",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scene_image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort", sa.Integer, nullable=False, default=0),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint("product_id", "scene_image_id"),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_image_id"], ["scene_image.id"], ondelete="CASCADE"),
    )

    op.execute("""
        CREATE TRIGGER update_scene_image_updated_at
        BEFORE UPDATE ON "scene_image"
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.execute("""
        CREATE TRIGGER update_product_scene_image_updated_at
        BEFORE UPDATE ON "product_scene_image"
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS update_product_scene_image_updated_at ON product_scene_image")
    op.execute("DROP TRIGGER IF EXISTS update_scene_image_updated_at ON scene_image")

    op.drop_table("product_scene_image")
    op.drop_table("scene_image")