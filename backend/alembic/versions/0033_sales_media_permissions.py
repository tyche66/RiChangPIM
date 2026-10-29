"""sales_can_use_media_library

Track D：方案平面图需要业务员从媒体库选用 / 上传图片。

权限点本身在 0011_add_media_permissions 已存在，这里只补角色映射：
``sales`` 增加 ``media:view`` 与 ``media:upload``（不含 delete / replace，
业务员不能改动别人已经用在产品图上的文件）。

不新增权限码、不修改任一历史迁移；0001-0009 的哈希保持不变。

Revision ID: 0033_sales_media_permissions
Revises: 0032_proposal_floor_plans
Create Date: 2026-10-29
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
from sqlalchemy.sql import text

revision: str = "0033_sales_media_permissions"
down_revision: Union[str, None] = "0032_proposal_floor_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_CODE = "sales"
PERM_CODES = ("media:view", "media:upload")


def upgrade() -> None:
    for perm_code in PERM_CODES:
        op.get_bind().execute(
            text("""
                INSERT INTO role_permission (id, role_id, permission_id,
                                             create_time, update_time, is_deleted)
                SELECT :id, r.id, p.id, now(), now(), false
                FROM role r, permission p
                WHERE r.role_code = :role_code
                  AND p.perm_code = :perm_code
                  AND r.is_deleted = false
                  AND p.is_deleted = false
                  AND NOT EXISTS (
                      SELECT 1 FROM role_permission rp
                      WHERE rp.role_id = r.id
                        AND rp.permission_id = p.id
                        AND rp.is_deleted = false
                  )
            """),
            {"id": str(uuid4()), "role_code": ROLE_CODE, "perm_code": perm_code},
        )


def downgrade() -> None:
    for perm_code in PERM_CODES:
        op.get_bind().execute(
            text("""
                DELETE FROM role_permission rp
                USING role r, permission p
                WHERE rp.role_id = r.id
                  AND rp.permission_id = p.id
                  AND r.role_code = :role_code
                  AND p.perm_code = :perm_code
            """),
            {"role_code": ROLE_CODE, "perm_code": perm_code},
        )
