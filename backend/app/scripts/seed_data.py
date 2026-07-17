"""装后种子数据运行脚本（与 alembic/versions/0004_seed_data.py 内容保持一致）。

用途：
- 在 ``alembic upgrade head`` 之后单独执行，作为「非迁移」路径的装后种子入口；
- 与 0004 数据迁移互为双保险：二者都幂等，重复执行不会重复插入；
- 额外确保初始 admin 用户存在（与 init_admin.py 职责一致，但更完整）。

执行：
    python -m app.scripts.seed_data            # 装后种子（含 admin 用户）
    python -m app.scripts.seed_data --check     # 仅校验，不写入
    python -m app.scripts.seed_data --no-admin  # 仅角色/权限/映射，不创建 admin 用户

注意：role/permission/role_permission 的「数据定义」必须与 0004_seed_data.py 保持同步。
"""

import argparse
import asyncio
import os
import sys
from uuid import uuid4

# 解析到 backend/ 项目根，不依赖启动目录（CWD），便于直接执行或迁移工具调用。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, Base, engine
from app.core.security import get_password_hash
from app.models.user import Permission, Role, RolePermission, User

# (role_code, role_name, description)
ROLES = [
    ("admin", "系统管理员", "拥有全部权限，含角色与权限管理"),
    ("purchaser", "采购员", "负责产品与供应商的维护"),
    ("sales", "销售员", "负责方案/报价/分享，查看产品信息"),
    ("viewer", "访客", "只读查看产品与统计看板"),
]

# (perm_code, perm_name, resource, action, type)
PERMISSIONS = [
    ("product:view", "产品查看", "product", "view", "read"),
    ("product:create", "产品新增", "product", "create", "write"),
    ("product:edit", "产品编辑", "product", "edit", "write"),
    ("product:delete", "产品删除", "product", "delete", "write"),
    ("product:import", "产品导入", "product", "import", "write"),
    ("product:export", "产品导出", "product", "export", "read"),
    ("product:status", "产品上下架", "product", "status", "write"),
    ("product:clone", "产品克隆", "product", "clone", "write"),
    ("category:view", "品类查看", "category", "view", "read"),
    ("category:create", "品类新增", "category", "create", "write"),
    ("category:edit", "品类编辑", "category", "edit", "write"),
    ("category:delete", "品类删除", "category", "delete", "write"),
    ("brand:view", "品牌查看", "brand", "view", "read"),
    ("brand:create", "品牌新增", "brand", "create", "write"),
    ("brand:edit", "品牌编辑", "brand", "edit", "write"),
    ("brand:delete", "品牌删除", "brand", "delete", "write"),
    ("tag:view", "标签查看", "tag", "view", "read"),
    ("tag:create", "标签新增", "tag", "create", "write"),
    ("tag:edit", "标签编辑", "tag", "edit", "write"),
    ("tag:delete", "标签删除", "tag", "delete", "write"),
    ("supplier:view", "供应商查看", "supplier", "view", "read"),
    ("supplier:create", "供应商新增", "supplier", "create", "write"),
    ("supplier:edit", "供应商编辑", "supplier", "edit", "write"),
    ("supplier:delete", "供应商删除", "supplier", "delete", "write"),
    ("user:view", "用户查看", "user", "view", "read"),
    ("user:create", "用户新增", "user", "create", "write"),
    ("user:edit", "用户编辑", "user", "edit", "write"),
    ("user:disable", "用户停用", "user", "disable", "write"),
    ("user:delete", "用户删除", "user", "delete", "write"),
    ("role:view", "角色查看", "role", "view", "read"),
    ("role:create", "角色新增", "role", "create", "write"),
    ("role:edit", "角色编辑", "role", "edit", "write"),
    ("role:delete", "角色删除", "role", "delete", "write"),
    ("role:assign", "角色授权", "role", "assign", "write"),
    ("proposal:view", "方案查看", "proposal", "view", "read"),
    ("proposal:create", "方案新增", "proposal", "create", "write"),
    ("proposal:edit", "方案编辑", "proposal", "edit", "write"),
    ("proposal:confirm", "方案确认", "proposal", "confirm", "write"),
    ("proposal:delete", "方案删除", "proposal", "delete", "write"),
    ("quotation:view", "报价查看", "quotation", "view", "read"),
    ("quotation:create", "报价新增", "quotation", "create", "write"),
    ("quotation:edit", "报价编辑", "quotation", "edit", "write"),
    ("quotation:confirm", "报价确认", "quotation", "confirm", "write"),
    ("quotation:delete", "报价删除", "quotation", "delete", "write"),
    ("share:view", "分享查看", "share", "view", "read"),
    ("share:create", "分享创建", "share", "create", "write"),
    ("share:delete", "分享删除", "share", "delete", "write"),
    ("file:view", "文件查看", "file", "view", "read"),
    ("file:upload", "文件上传", "file", "upload", "write"),
    ("file:delete", "文件删除", "file", "delete", "write"),
    ("stats:view", "统计查看", "stats", "view", "read"),
    ("audit:view", "审计日志查看", "audit", "view", "read"),
    ("ai:use", "AI 能力使用", "ai", "use", "write"),
]

# 角色 -> 权限映射；"*" 表示全部权限点
ROLE_PERMISSIONS = {
    "admin": ["*"],
    "purchaser": [
        "product:view",
        "product:create",
        "product:edit",
        "product:delete",
        "product:import",
        "product:export",
        "product:status",
        "product:clone",
        "category:view",
        "category:create",
        "category:edit",
        "category:delete",
        "brand:view",
        "brand:create",
        "brand:edit",
        "brand:delete",
        "tag:view",
        "tag:create",
        "tag:edit",
        "tag:delete",
        "supplier:view",
        "supplier:create",
        "supplier:edit",
        "supplier:delete",
        "file:view",
        "file:upload",
        "stats:view",
    ],
    "sales": [
        "product:view",
        "product:export",
        "proposal:view",
        "proposal:create",
        "proposal:edit",
        "proposal:delete",
        "quotation:view",
        "quotation:create",
        "quotation:edit",
        "quotation:delete",
        "share:view",
        "share:create",
        "share:delete",
        "file:view",
        "file:upload",
        "stats:view",
        "ai:use",
    ],
    "viewer": [
        "product:view",
        "stats:view",
    ],
}

ADMIN_USERNAME = "admin"


def _expand(perm_codes):
    if perm_codes == ["*"]:
        return [p[0] for p in PERMISSIONS]
    return perm_codes


async def _ensure_roles(db, check_only):
    created = 0
    for code, name, desc in ROLES:
        exist = (
            await db.execute(select(Role).where(Role.role_code == code, Role.is_deleted.is_(False)))
        ).scalar_one_or_none()
        if exist:
            continue
        if check_only:
            print(f"  [check] 角色缺失: {code}")
            created += 1
            continue
        db.add(Role(id=uuid4(), role_name=name, role_code=code, description=desc))
        created += 1
        print(f"  创建角色: {code} ({name})")
    return created


async def _ensure_permissions(db, check_only):
    created = 0
    for perm_code, perm_name, resource, action, ptype in PERMISSIONS:
        exist = (
            await db.execute(
                select(Permission).where(
                    Permission.perm_code == perm_code, Permission.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if exist:
            continue
        if check_only:
            print(f"  [check] 权限缺失: {perm_code}")
            created += 1
            continue
        db.add(
            Permission(
                id=uuid4(),
                perm_code=perm_code,
                perm_name=perm_name,
                resource=resource,
                action=action,
                type=ptype,
            )
        )
        created += 1
        print(f"  创建权限: {perm_code}")
    return created


async def _ensure_role_permissions(db, check_only):
    created = 0
    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        role = (
            await db.execute(
                select(Role).where(Role.role_code == role_code, Role.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if not role:
            continue
        for pc in _expand(perm_codes):
            perm = (
                await db.execute(
                    select(Permission).where(
                        Permission.perm_code == pc, Permission.is_deleted.is_(False)
                    )
                )
            ).scalar_one_or_none()
            if not perm:
                continue
            exist = (
                await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm.id,
                        RolePermission.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if exist:
                continue
            if check_only:
                print(f"  [check] 映射缺失: {role_code} -> {pc}")
                created += 1
                continue
            db.add(RolePermission(id=uuid4(), role_id=role.id, permission_id=perm.id))
            created += 1
    return created


async def _ensure_admin_user(db, check_only):
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not check_only and not admin_password:
        raise RuntimeError("ADMIN_PASSWORD is required when creating the admin user")
    role = (
        await db.execute(select(Role).where(Role.role_code == "admin", Role.is_deleted.is_(False)))
    ).scalar_one_or_none()
    if not role:
        # 角色种子本应在同一次 seed 中先于用户写入；若仍缺失，说明种子流程异常，
        # 必须作为真实失败退出（非零），不得静默跳过导致“看似成功”。
        raise RuntimeError("admin 角色不存在，无法创建初始管理员用户，请检查角色种子是否成功写入")
    exist = (
        await db.execute(
            select(User).where(User.username == ADMIN_USERNAME, User.is_deleted.is_(False))
        )
    ).scalar_one_or_none()
    if exist:
        return 0
    if check_only:
        print(f"  [check] admin 用户缺失: {ADMIN_USERNAME}")
        return 1
    db.add(
        User(
            id=uuid4(),
            username=ADMIN_USERNAME,
            password_hash=get_password_hash(admin_password),
            role_id=role.id,
            status="active",
        )
    )
    print(f"  创建 admin 用户: {ADMIN_USERNAME}")
    return 1


async def seed(check_only: bool, with_admin: bool):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        print("== 角色 ==")
        rc = await _ensure_roles(db, check_only)
        print("== 权限 ==")
        pc = await _ensure_permissions(db, check_only)
        print("== 角色-权限映射 ==")
        rpc = await _ensure_role_permissions(db, check_only)
        ac = 0
        if with_admin:
            print("== admin 用户 ==")
            ac = await _ensure_admin_user(db, check_only)
        await db.commit()

    total = rc + pc + rpc + ac
    if check_only:
        print(f"[check] 共缺失 {total} 条种子；加 --no-admin 不影响角色/权限校验。")
    else:
        print(f"[done] 本次新增 {total} 条种子（已存在则跳过）。")
    return total


def main():
    parser = argparse.ArgumentParser(description="AI-PIM 装后种子数据脚本")
    parser.add_argument("--check", action="store_true", help="仅校验缺失项，不写入")
    parser.add_argument("--no-admin", action="store_true", help="不创建 admin 用户")
    args = parser.parse_args()

    asyncio.run(seed(check_only=args.check, with_admin=not args.no_admin))


if __name__ == "__main__":
    main()
