import asyncio
import os
import sys
from uuid import uuid4

# 解析到 backend/ 项目根，不依赖启动目录（CWD），便于直接执行或迁移工具调用。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, Base, engine
from app.core.security import get_password_hash
from app.models.user import Role, User


async def init_admin():
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        raise RuntimeError("ADMIN_PASSWORD is required")

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

        if not admin_user:
            admin_user = User(
                id=uuid4(),
                username=admin_username,
                password_hash=get_password_hash(admin_password),
                role_id=admin_role.id,
                status="active",
            )
            db.add(admin_user)
            print(f"初始管理员已创建: {admin_username}")
        else:
            admin_user.password_hash = get_password_hash(admin_password)
            admin_user.role_id = admin_role.id
            admin_user.status = "active"
            print(f"管理员凭据已从受控环境变量同步: {admin_username}")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(init_admin())
