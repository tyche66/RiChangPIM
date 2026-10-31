import asyncio
import os
import sys
from uuid import uuid4

# 解析到 backend/ 项目根，不依赖启动目录（CWD），便于直接执行或迁移工具调用。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, Base, engine
from app.core.security import get_password_hash, verify_password
from app.models.user import Role, User

SEED_DEFAULT_PASSWORD = "admin123"


def _validate_bootstrap_password(password: str) -> None:
    if "REPLACE_ME" in password.upper():
        raise RuntimeError("ADMIN_PASSWORD still contains the example placeholder")
    if password == SEED_DEFAULT_PASSWORD:
        raise RuntimeError("ADMIN_PASSWORD must not be the seeded default")
    if len(password) < 12:
        raise RuntimeError("ADMIN_PASSWORD must be at least 12 characters")
    if len(password.encode("utf-8")) > 72:
        raise RuntimeError("ADMIN_PASSWORD must not exceed 72 bytes")


async def init_admin():
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        raise RuntimeError("ADMIN_PASSWORD is required")
    reset_requested = os.environ.get("ADMIN_PASSWORD_RESET", "0") == "1"

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Role).where(Role.role_code == "admin"))
        admin_role = result.scalar_one_or_none()

        if not admin_role:
            admin_role = Role(
                id=uuid4(),
                role_name="系统管理员",
                role_code="admin",
                description="拥有全部权限，含角色与权限管理",
            )
            db.add(admin_role)
            await db.flush()

        result = await db.execute(select(User).where(User.username == admin_username))
        admin_user = result.scalar_one_or_none()

        if admin_user and admin_user.is_deleted:
            raise RuntimeError(
                "ADMIN_USERNAME belongs to a soft-deleted account; resolve it manually"
            )

        if not admin_user:
            _validate_bootstrap_password(admin_password)
            admin_user = User(
                id=uuid4(),
                username=admin_username,
                password_hash=get_password_hash(admin_password),
                role_id=admin_role.id,
                status="active",
            )
            db.add(admin_user)
            print(f"初始管理员已创建: {admin_username}")
        elif reset_requested:
            _validate_bootstrap_password(admin_password)
            admin_user.password_hash = get_password_hash(admin_password)
            admin_user.token_version = (admin_user.token_version or 0) + 1
            print(f"管理员密码已按 ADMIN_PASSWORD_RESET=1 重置: {admin_username}")
        elif verify_password(SEED_DEFAULT_PASSWORD, admin_user.password_hash):
            _validate_bootstrap_password(admin_password)
            admin_user.password_hash = get_password_hash(admin_password)
            admin_user.token_version = (admin_user.token_version or 0) + 1
            print(f"检测到种子默认管理员密码，已替换为受控环境变量值: {admin_username}")
        else:
            print(f"管理员已存在，保持现有密码/角色/状态不变: {admin_username}")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(init_admin())
