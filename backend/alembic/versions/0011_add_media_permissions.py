"""add_media_permissions

新增媒体库与场景图独立权限点，用于精细化权限控制。

新增权限点：
  - media:view, media:upload, media:delete, media:replace
  - scene_image:view, scene_image:create, scene_image:edit, scene_image:delete

角色映射变更：
  - admin: 全部（* 自动覆盖）
  - purchaser: 新增 media:view, media:upload, media:delete, media:replace
  - sales: 新增 scene_image:view, scene_image:create, scene_image:edit, scene_image:delete
  - viewer: 新增 media:view, scene_image:view

Revision ID: 0011_add_media_permissions
Revises: 0010_add_scene_image
Create Date: 2026-07-21
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
from sqlalchemy.sql import text

revision: str = "0011_add_media_permissions"
down_revision: Union[str, None] = "0010_add_scene_image"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSIONS = [
    ("media:view", "媒体库查看", "media", "view", "read"),
    ("media:upload", "媒体库上传", "media", "upload", "write"),
    ("media:delete", "媒体库删除", "media", "delete", "write"),
    ("media:replace", "媒体库替换", "media", "replace", "write"),
    ("scene_image:view", "场景图查看", "scene_image", "view", "read"),
    ("scene_image:create", "场景图新增", "scene_image", "create", "write"),
    ("scene_image:edit", "场景图编辑", "scene_image", "edit", "write"),
    ("scene_image:delete", "场景图删除", "scene_image", "delete", "write"),
]

ROLE_PERMISSION_MAP = {
    "admin": ["*"],
    "purchaser": [
        "media:view", "media:upload", "media:delete", "media:replace",
    ],
    "sales": [
        "scene_image:view", "scene_image:create", "scene_image:edit", "scene_image:delete",
    ],
    "viewer": [
        "media:view", "scene_image:view",
    ],
}

ALL_NEW_CODES = {p[0] for p in NEW_PERMISSIONS}

ALL_PERM_CODES = [p[0] for p in NEW_PERMISSIONS]


def _expand(perm_codes):
    if perm_codes == ["*"]:
        return list(ALL_NEW_CODES)
    return perm_codes


def upgrade() -> None:
    for perm_code, perm_name, resource, action, ptype in NEW_PERMISSIONS:
        op.get_bind().execute(
            text("""
                INSERT INTO permission (id, perm_code, perm_name, resource,
                                        action, type, create_time, update_time, is_deleted)
                SELECT :id, :perm_code, :perm_name, :resource,
                       :action, :type, now(), now(), false
                WHERE NOT EXISTS (
                    SELECT 1 FROM permission
                    WHERE perm_code = :perm_code AND is_deleted = false
                )
            """),
            {
                "id": str(uuid4()),
                "perm_code": perm_code,
                "perm_name": perm_name,
                "resource": resource,
                "action": action,
                "type": ptype,
            },
        )

    for role_code, perm_codes in ROLE_PERMISSION_MAP.items():
        for pc in _expand(perm_codes):
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
                {"id": str(uuid4()), "role_code": role_code, "perm_code": pc},
            )


def downgrade() -> None:
    for role_code, perm_codes in ROLE_PERMISSION_MAP.items():
        for pc in _expand(perm_codes):
            op.get_bind().execute(
                text("""
                    DELETE FROM role_permission rp
                    USING role r, permission p
                    WHERE rp.role_id = r.id
                      AND rp.permission_id = p.id
                      AND r.role_code = :role_code
                      AND p.perm_code = :perm_code
                """),
                {"role_code": role_code, "perm_code": pc},
            )

    for perm_code in ALL_PERM_CODES:
        op.get_bind().execute(
            text("""
                DELETE FROM permission
                WHERE perm_code = :perm_code AND is_deleted = false
            """),
            {"perm_code": perm_code},
        )
