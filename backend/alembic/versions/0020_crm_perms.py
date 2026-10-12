"""crm_perms

CRM-Lite 权限种子：16 个新权限码 + manager/designer/operator 三角色 + 映射。

权限码（HLD §6.1）：
  customer:view/edit/pii/export/transfer
  project:view/edit/member/asset
  dashboard:view
  content:view/generate/adopt/publish/metric
  reminder:edit

角色（HLD §6.2）：admin/manager/sales/designer/operator/purchaser/viewer

Revision ID: 0020_crm_perms
Revises: 0017_operation_log_username
Create Date: 2026-10-10
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
from sqlalchemy.sql import text

revision: str = "0020_crm_perms"
down_revision: Union[str, None] = "0017_operation_log_username"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (perm_code, perm_name, resource, action, type)
NEW_PERMISSIONS = [
    ("customer:view", "客户查看", "customer", "view", "read"),
    ("customer:edit", "客户编辑", "customer", "edit", "write"),
    ("customer:pii", "客户明文查看", "customer", "pii", "read"),
    ("customer:export", "客户导出", "customer", "export", "read"),
    ("customer:transfer", "客户移交", "customer", "transfer", "write"),
    ("project:view", "项目查看", "project", "view", "read"),
    ("project:edit", "项目编辑", "project", "edit", "write"),
    ("project:member", "项目成员管理", "project", "member", "write"),
    ("project:asset", "项目图纸管理", "project", "asset", "write"),
    ("dashboard:view", "驾驶舱查看", "dashboard", "view", "read"),
    ("content:view", "内容查看", "content", "view", "read"),
    ("content:generate", "内容生成", "content", "generate", "write"),
    ("content:adopt", "内容采纳", "content", "adopt", "write"),
    ("content:publish", "内容发布", "content", "publish", "write"),
    ("content:metric", "内容曝光", "content", "metric", "write"),
    ("reminder:edit", "提醒管理", "reminder", "edit", "write"),
    # scene_image 补录（G0-4.8 漂移修复）
    ("scene_image:view", "场景图查看", "scene_image", "view", "read"),
    ("scene_image:create", "场景图新增", "scene_image", "create", "write"),
    ("scene_image:edit", "场景图编辑", "scene_image", "edit", "write"),
    ("scene_image:delete", "场景图删除", "scene_image", "delete", "write"),
]

# (role_code, role_name, description)
NEW_ROLES = [
    ("manager", "经理", "数据范围全量、无 user/role/系统码"),
    ("designer", "设计师", "绑定项目内可见；无 customer:view"),
    ("operator", "运营", "内容工坊操作；无 customer:/project: 码"),
]

# 角色 -> 权限映射（HLD §6.2 矩阵）
ROLE_PERMISSION_MAP = {
    "admin": ["*"],
    "manager": [
        "customer:view", "customer:edit", "customer:pii",
        "customer:export", "customer:transfer",
        "project:view", "project:edit", "project:member", "project:asset",
        "dashboard:view",
        "content:view", "content:generate", "content:adopt",
        "content:publish", "content:metric",
        "reminder:edit",
    ],
    "sales": [
        "customer:view", "customer:edit", "customer:pii",
        "project:view", "project:edit", "project:member", "project:asset",
        "dashboard:view",
        "content:view",
        "reminder:edit",
    ],
    "designer": [
        "project:view", "project:asset",
        "dashboard:view",
        "reminder:edit",
    ],
    "operator": [
        "dashboard:view",
        "content:view", "content:generate", "content:adopt",
        "content:publish", "content:metric",
        "reminder:edit",
    ],
}

ALL_NEW_CODES = {p[0] for p in NEW_PERMISSIONS}


def _expand(perm_codes):
    if perm_codes == ["*"]:
        return list(ALL_NEW_CODES)
    return perm_codes


def upgrade() -> None:
    # 1) 新角色
    for code, name, desc in NEW_ROLES:
        op.get_bind().execute(
            text("""
                INSERT INTO role (id, role_name, role_code, description,
                                  create_time, update_time, is_deleted)
                SELECT :id, :name, :code, :desc, now(), now(), false
                WHERE NOT EXISTS (
                    SELECT 1 FROM role
                    WHERE role_code = :code AND is_deleted = false
                )
            """),
            {"id": str(uuid4()), "name": name, "code": code, "desc": desc},
        )

    # 2) 新权限
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

    # 3) 角色-权限映射
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

    for perm_code in ALL_NEW_CODES:
        op.get_bind().execute(
            text("""
                DELETE FROM permission
                WHERE perm_code = :perm_code AND is_deleted = false
            """),
            {"perm_code": perm_code},
        )

    for code, _, _ in NEW_ROLES:
        op.get_bind().execute(
            text("""
                DELETE FROM role
                WHERE role_code = :code
                  AND is_deleted = false
                  AND NOT EXISTS (
                      SELECT 1 FROM "user" u WHERE u.role_id = role.id
                  )
            """),
            {"code": code},
        )
