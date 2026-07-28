"""ai_permissions

Revision ID: 0013_ai_permissions
Revises: 0012_product_scene_image_partial_unique
Create Date: 2026-07-25 00:00:00.000000
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
from sqlalchemy.sql import text

revision: str = "0013_ai_permissions"
down_revision: Union[str, None] = "0012_product_scene_image_partial_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PERMISSIONS = [
    ("ai:access", "AI 助手访问", "ai", "access", "read"),
    ("ai:product", "AI 产品查询", "ai", "product", "read"),
    ("ai:knowledge", "AI 知识问答", "ai", "knowledge", "read"),
    ("ai:quality", "AI 质量查询", "ai", "quality", "read"),
    ("ai:procurement", "AI 采购查询", "ai", "procurement", "read"),
    ("knowledge:manage", "知识索引管理", "knowledge", "manage", "write"),
    ("knowledge:debug", "知识调试", "knowledge", "debug", "read"),
]

ROLE_PERMISSIONS = {
    "admin": [perm[0] for perm in PERMISSIONS],
    "purchaser": ["ai:access", "ai:product", "ai:knowledge", "ai:quality", "ai:procurement"],
    "sales": ["ai:access", "ai:product", "ai:knowledge"],
    "viewer": ["ai:access", "ai:knowledge"],
}


def upgrade() -> None:
    bind = op.get_bind()
    for perm_code, perm_name, resource, action, ptype in PERMISSIONS:
        bind.execute(
            text(
                """
                INSERT INTO permission (id, perm_code, perm_name, resource, action, type, create_time, update_time, is_deleted)
                SELECT :id, :perm_code, :perm_name, :resource, :action, :type, now(), now(), false
                WHERE NOT EXISTS (SELECT 1 FROM permission WHERE perm_code = :perm_code AND is_deleted = false)
                """
            ),
            {"id": str(uuid4()), "perm_code": perm_code, "perm_name": perm_name, "resource": resource, "action": action, "type": ptype},
        )
    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        for perm_code in perm_codes:
            bind.execute(
                text(
                    """
                    INSERT INTO role_permission (id, role_id, permission_id, create_time, update_time, is_deleted)
                    SELECT :id, r.id, p.id, now(), now(), false
                    FROM role r, permission p
                    WHERE r.role_code = :role_code AND p.perm_code = :perm_code
                      AND r.is_deleted = false AND p.is_deleted = false
                      AND NOT EXISTS (
                        SELECT 1 FROM role_permission rp
                        WHERE rp.role_id = r.id AND rp.permission_id = p.id AND rp.is_deleted = false
                      )
                    """
                ),
                {"id": str(uuid4()), "role_code": role_code, "perm_code": perm_code},
            )


def downgrade() -> None:
    bind = op.get_bind()
    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        for perm_code in perm_codes:
            bind.execute(
                text(
                    """
                    DELETE FROM role_permission rp
                    USING role r, permission p
                    WHERE rp.role_id = r.id AND rp.permission_id = p.id
                      AND r.role_code = :role_code AND p.perm_code = :perm_code
                    """
                ),
                {"role_code": role_code, "perm_code": perm_code},
            )
    for perm_code, *_ in PERMISSIONS:
        bind.execute(text("DELETE FROM permission WHERE perm_code = :perm_code"), {"perm_code": perm_code})
