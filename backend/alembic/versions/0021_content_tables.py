"""content_tables

新媒体内容工坊表：content_batches / content_items / content_publications /
content_metric_snapshots。

Revision ID: 0021_content_tables
Revises: 0020_crm_perms
Create Date: 2026-10-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0021_content_tables"
down_revision: Union[str, None] = "0020_crm_perms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # content_batches
    op.create_table(
        "content_batches",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("customer_id", PGUUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_id", PGUUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_ids", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("tone", sa.String(32), nullable=True),
        sa.Column("requested_count", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'running'"), nullable=False),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("model_provider", sa.String(32), nullable=True),
        sa.Column("model_name", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(16), server_default=sa.text("'v1'"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("platform IN ('xhs','douyin','moments','seo','other')", name="ck_cb_platform"),
        sa.CheckConstraint("status IN ('pending','running','done','failed')", name="ck_cb_status"),
        sa.CheckConstraint("requested_count BETWEEN 1 AND 5", name="ck_cb_count"),
    )
    op.create_index("ix_cb_created", "content_batches", ["create_time"], postgresql_where=sa.text("is_deleted = false"))

    # content_items
    op.create_table(
        "content_items",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("batch_id", PGUUID(as_uuid=True), sa.ForeignKey("content_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_type", sa.String(16), server_default=sa.text("'copy'"), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("hashtags", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("adopted_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.String(255), nullable=True),
        sa.Column("produced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("verified_payload", JSONB(), nullable=True),
        sa.Column("warnings", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("external_ref", sa.String(128), nullable=True),
        sa.Column("model_provider", sa.String(32), nullable=True),
        sa.Column("model_name", sa.String(64), nullable=True),
        sa.Column("generation_version", sa.String(16), server_default=sa.text("'v1'"), nullable=False),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("item_type IN ('copy','video_script')", name="ck_ci_type"),
        sa.CheckConstraint("status IN ('draft','adopted','rejected','produced','published')", name="ck_ci_status"),
        sa.CheckConstraint("char_length(body) <= 20000", name="ck_ci_len"),
    )
    op.create_index("ix_ci_batch", "content_items", ["batch_id"], postgresql_where=sa.text("is_deleted = false"))
    op.create_index("ix_ci_status", "content_items", ["status", "create_time"], postgresql_where=sa.text("is_deleted = false"))

    # content_publications
    op.create_table(
        "content_publications",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("content_item_id", PGUUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("account_name", sa.String(128), nullable=True),
        sa.Column("publish_url", sa.String(1024), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("video_attachment_id", PGUUID(as_uuid=True), sa.ForeignKey("attachment.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_ref", sa.String(128), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
    )
    op.create_index("uq_pub_item_url", "content_publications", ["content_item_id", "publish_url"], unique=True, postgresql_where=sa.text("is_deleted = false"))
    op.create_index("ix_pub_published", "content_publications", ["published_at"], postgresql_where=sa.text("is_deleted = false"))

    # content_metric_snapshots
    op.create_table(
        "content_metric_snapshots",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("publication_id", PGUUID(as_uuid=True), sa.ForeignKey("content_publications.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("favorites", sa.Integer(), nullable=True),
        sa.Column("leads", sa.Integer(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("captured_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(8), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by", PGUUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("source IN ('manual','import')", name="ck_cms_source"),
        sa.CheckConstraint(
            "coalesce(views,0)>=0 AND coalesce(likes,0)>=0 AND coalesce(comments,0)>=0 "
            "AND coalesce(shares,0)>=0 AND coalesce(favorites,0)>=0 AND coalesce(leads,0)>=0",
            name="ck_cms_nonneg",
        ),
    )
    op.create_index("uq_cms_pub_date", "content_metric_snapshots", ["publication_id", "captured_date"], unique=True, postgresql_where=sa.text("is_deleted = false"))
    op.create_index("ix_cms_pub_time", "content_metric_snapshots", ["publication_id", "captured_at"], postgresql_where=sa.text("is_deleted = false"))


def downgrade() -> None:
    op.drop_table("content_metric_snapshots")
    op.drop_table("content_publications")
    op.drop_table("content_items")
    op.drop_table("content_batches")
