"""add_product_scene_image_partial_unique_index

新增 product_scene_image 的局部唯一索引 `idx_product_scene_image_active`，
确保每对 (product_id, scene_image_id) 在 is_deleted=false 时唯一不重复。

这解决了「解绑后重新绑定同一场景图时组合主键冲突」的问题：
解绑只设 is_deleted=true 不删行，重新绑定时恢复旧行或插入新行；
由于 is_deleted=true 的行不受索引限制，不存在冲突。

Revision ID: 0012_product_scene_image_partial_unique
Revises: 0011_add_media_permissions
Create Date: 2026-07-21
"""

from alembic import op

revision: str = "0012_product_scene_image_partial_unique"
down_revision: str | None = "0011_add_media_permissions"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Alembic creates version_num as VARCHAR(32), while this released revision
    # identifier is longer. Widen it before Alembic records the new revision.
    op.execute(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(64)"
    )
    op.create_index(
        "idx_product_scene_image_active",
        "product_scene_image",
        ["product_id", "scene_image_id"],
        unique=True,
        postgresql_where="is_deleted = false",
    )


def downgrade() -> None:
    op.drop_index("idx_product_scene_image_active", table_name="product_scene_image")
