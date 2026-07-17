"""seed_data

初始化种子数据迁移（ERD V1 装后种子）。

与 docs/03 §十二「初始化种子数据」的 INSERT 保持一致，作为 Alembic 数据迁移
在「模型建表（0001/0002/0003）」之后补入基础 RBAC 数据：

1. role 表：admin / purchaser / sales / viewer 四个基础角色
2. permission 表：产品 / 供应商 / 角色 / 用户 / 品类 / 品牌 / 标签 /
   方案 / 报价 / 分享 / 文件 / 统计 / AI 等职能模块的权限点
3. role_permission 表：将上述权限按角色职责装配成角色-权限映射

幂等：upgrade 通过 NOT EXISTS 守卫，重复执行不会重复插入或报错；
downgrade 按 code 反向清理种子数据（仅删除无用户引用的角色，避免外键冲突）。

Revision ID: 0004_seed_data
Revises: 0003_add_quotation_subtotal
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union
from uuid import NAMESPACE_DNS, uuid4, uuid5

from alembic import op
from sqlalchemy.sql import text

# 迁移所创建「初始管理员」的稳定标识（ownership 锚点）。
#
# 历史实现：0004 upgrade 仅在 admin 不存在时插入用户，但 downgrade 无条件按
# ``username = 'admin'`` 删除。若升级前业务库已存在 admin 用户，rollback 会误删
# 升级前已有的有效业务数据。
#
# 修复：本迁移创建的管理员使用*确定性 UUID*（由固定命名空间 + 固定名称派生），
# 因此只有这条记录能由本迁移「拥有」。downgrade 仅删除该固定 id 的用户；任何
# 升级前已存在（随机 id）的 admin 都不会被波及。重复 upgrade 受 NOT EXISTS 守卫
# 幂等；downgrade 后再 upgrade 以同一确定性 id 重建，行为可解释、可复现。
ADMIN_MIGRATION_ID = uuid5(NAMESPACE_DNS, "ai_pim.0004_seed_data.admin")

# revision identifiers, used by Alembic.
revision: str = "0004_seed_data"
down_revision: Union[str, None] = "0003_add_quotation_subtotal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (role_code, role_name, description)
ROLES = [
    ("admin", "系统管理员", "拥有全部权限，含角色与权限管理"),
    ("purchaser", "采购员", "负责产品与供应商的维护"),
    ("sales", "销售员", "负责方案/报价/分享，查看产品信息"),
    ("viewer", "访客", "只读查看产品与统计看板"),
]

# (perm_code, perm_name, resource, action, type)
# type: read=查看类, write=写入/变更类
PERMISSIONS = [
    # 产品
    ("product:view", "产品查看", "product", "view", "read"),
    ("product:create", "产品新增", "product", "create", "write"),
    ("product:edit", "产品编辑", "product", "edit", "write"),
    ("product:delete", "产品删除", "product", "delete", "write"),
    ("product:import", "产品导入", "product", "import", "write"),
    ("product:export", "产品导出", "product", "export", "read"),
    ("product:status", "产品上下架", "product", "status", "write"),
    ("product:clone", "产品克隆", "product", "clone", "write"),
    # 品类
    ("category:view", "品类查看", "category", "view", "read"),
    ("category:create", "品类新增", "category", "create", "write"),
    ("category:edit", "品类编辑", "category", "edit", "write"),
    ("category:delete", "品类删除", "category", "delete", "write"),
    # 品牌
    ("brand:view", "品牌查看", "brand", "view", "read"),
    ("brand:create", "品牌新增", "brand", "create", "write"),
    ("brand:edit", "品牌编辑", "brand", "edit", "write"),
    ("brand:delete", "品牌删除", "brand", "delete", "write"),
    # 标签
    ("tag:view", "标签查看", "tag", "view", "read"),
    ("tag:create", "标签新增", "tag", "create", "write"),
    ("tag:edit", "标签编辑", "tag", "edit", "write"),
    ("tag:delete", "标签删除", "tag", "delete", "write"),
    # 供应商
    ("supplier:view", "供应商查看", "supplier", "view", "read"),
    ("supplier:create", "供应商新增", "supplier", "create", "write"),
    ("supplier:edit", "供应商编辑", "supplier", "edit", "write"),
    ("supplier:delete", "供应商删除", "supplier", "delete", "write"),
    # 用户
    ("user:view", "用户查看", "user", "view", "read"),
    ("user:create", "用户新增", "user", "create", "write"),
    ("user:edit", "用户编辑", "user", "edit", "write"),
    ("user:delete", "用户删除", "user", "delete", "write"),
    # 角色与权限
    ("role:view", "角色查看", "role", "view", "read"),
    ("role:create", "角色新增", "role", "create", "write"),
    ("role:edit", "角色编辑", "role", "edit", "write"),
    ("role:delete", "角色删除", "role", "delete", "write"),
    ("role:assign", "角色授权", "role", "assign", "write"),
    # 方案
    ("proposal:view", "方案查看", "proposal", "view", "read"),
    ("proposal:create", "方案新增", "proposal", "create", "write"),
    ("proposal:edit", "方案编辑", "proposal", "edit", "write"),
    ("proposal:delete", "方案删除", "proposal", "delete", "write"),
    # 报价
    ("quotation:view", "报价查看", "quotation", "view", "read"),
    ("quotation:create", "报价新增", "quotation", "create", "write"),
    ("quotation:edit", "报价编辑", "quotation", "edit", "write"),
    ("quotation:delete", "报价删除", "quotation", "delete", "write"),
    # 分享
    ("share:view", "分享查看", "share", "view", "read"),
    ("share:create", "分享创建", "share", "create", "write"),
    ("share:delete", "分享删除", "share", "delete", "write"),
    # 文件
    ("file:view", "文件查看", "file", "view", "read"),
    ("file:upload", "文件上传", "file", "upload", "write"),
    ("file:delete", "文件删除", "file", "delete", "write"),
    # 统计
    ("stats:view", "统计查看", "stats", "view", "read"),
    # AI
    ("ai:use", "AI 能力使用", "ai", "use", "write"),
]

# 角色 -> 权限映射；"*" 表示全部权限点
ROLE_PERMISSIONS = {
    "admin": ["*"],
    "purchaser": [
        "product:view", "product:create", "product:edit", "product:delete",
        "product:import", "product:export", "product:status", "product:clone",
        "category:view", "category:create", "category:edit", "category:delete",
        "brand:view", "brand:create", "brand:edit", "brand:delete",
        "tag:view", "tag:create", "tag:edit", "tag:delete",
        "supplier:view", "supplier:create", "supplier:edit", "supplier:delete",
        "file:view", "file:upload", "stats:view",
    ],
    "sales": [
        "product:view", "product:export",
        "proposal:view", "proposal:create", "proposal:edit", "proposal:delete",
        "quotation:view", "quotation:create", "quotation:edit", "quotation:delete",
        "share:view", "share:create", "share:delete",
        "file:view", "file:upload", "stats:view", "ai:use",
    ],
    "viewer": [
        "product:view", "stats:view",
    ],
}


def _expand(perm_codes):
    if perm_codes == ["*"]:
        return [p[0] for p in PERMISSIONS]
    return perm_codes


def upgrade() -> None:
    # 1) role 种子
    for code, name, desc in ROLES:
        op.get_bind().execute(
            text(
                """
                INSERT INTO role (id, role_name, role_code, description,
                                  create_time, update_time, is_deleted)
                SELECT :id, :name, :code, :desc, now(), now(), false
                WHERE NOT EXISTS (
                    SELECT 1 FROM role
                    WHERE role_code = :code AND is_deleted = false
                )
                """
            ),
            {"id": str(uuid4()), "name": name, "code": code, "desc": desc},
        )

    # 2) permission 种子
    for perm_code, perm_name, resource, action, ptype in PERMISSIONS:
        op.get_bind().execute(
            text(
                """
                INSERT INTO permission (id, perm_code, perm_name, resource,
                                        action, type, create_time, update_time, is_deleted)
                SELECT :id, :perm_code, :perm_name, :resource,
                       :action, :type, now(), now(), false
                WHERE NOT EXISTS (
                    SELECT 1 FROM permission
                    WHERE perm_code = :perm_code AND is_deleted = false
                )
                """
            ),
            {
                "id": str(uuid4()),
                "perm_code": perm_code,
                "perm_name": perm_name,
                "resource": resource,
                "action": action,
                "type": ptype,
            },
        )

    # 3) role_permission 装配（按 code 关联，幂等守卫避免重复）
    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        for pc in _expand(perm_codes):
            op.get_bind().execute(
                text(
                    """
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
                    """
                ),
                {"id": str(uuid4()), "role_code": role_code, "perm_code": pc},
            )

    # 4) 初始管理员用户（admin / admin123），便于集成测试与首次登录。
    _seed_admin_user()


def _seed_admin_user() -> None:
    from app.core.security import get_password_hash

    op.get_bind().execute(
        text(
            """
            INSERT INTO "user" (id, username, password_hash, role_id, status,
                                create_time, update_time, is_deleted)
            SELECT :id, :username, :password_hash, r.id, 'active', now(), now(), false
            FROM role r
            WHERE r.role_code = 'admin' AND r.is_deleted = false
              AND NOT EXISTS (
                  SELECT 1 FROM "user" u
                  WHERE u.username = :username AND u.is_deleted = false
              )
            """
        ),
        {
            "id": str(ADMIN_MIGRATION_ID),
            "username": "admin",
            "password_hash": get_password_hash("admin123"),
        },
    )


def downgrade() -> None:
    seeded_role_codes = [r[0] for r in ROLES]
    seeded_perm_codes = [p[0] for p in PERMISSIONS]

    # 4) 清理初始管理员用户（仅删除本迁移以确定性 id 创建的用户）。
    #    升级前已存在的 admin（随机 id）不会被误删；重复 upgrade 受 NOT EXISTS
    #    守卫约束，本迁移至多插入一条固定 id 的 admin，downgrade 精确回滚该记录。
    op.get_bind().execute(
        text(
            """
            DELETE FROM "user"
            WHERE id = :admin_id AND is_deleted = false
            """
        ),
        {"admin_id": str(ADMIN_MIGRATION_ID)},
    )

    # 3) 清理 role_permission 关联
    op.get_bind().execute(
        text(
            """
            DELETE FROM role_permission rp
            USING role r, permission p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND (r.role_code = ANY(:role_codes) OR p.perm_code = ANY(:perm_codes))
            """
        ),
        {"role_codes": seeded_role_codes, "perm_codes": seeded_perm_codes},
    )

    # 2) 清理 permission 种子
    op.get_bind().execute(
        text(
            """
            DELETE FROM permission
            WHERE perm_code = ANY(:perm_codes) AND is_deleted = false
            """
        ),
        {"perm_codes": seeded_perm_codes},
    )

    # 1) 清理 role 种子（仅删除无用户引用的角色，避免外键冲突）
    for code in seeded_role_codes:
        op.get_bind().execute(
            text(
                """
                DELETE FROM role
                WHERE role_code = :code
                  AND is_deleted = false
                  AND NOT EXISTS (
                      SELECT 1 FROM "user" u WHERE u.role_id = role.id
                  )
                """
            ),
            {"code": code},
        )
