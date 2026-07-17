from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def load_user_perms(db: AsyncSession, user_id, role_id: str | None = None) -> list[str]:
    from app.models.user import Permission, RolePermission, User

    if role_id is None:
        result = await db.execute(
            select(User.role_id).where(User.id == user_id, User.is_deleted.is_(False))
        )
        row = result.first()
        if not row:
            return []
        role_id = row[0]

    perm_result = await db.execute(
        select(Permission.perm_code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(
            RolePermission.role_id == role_id,
            Permission.is_deleted.is_(False),
            RolePermission.is_deleted.is_(False),
        )
    )
    return [r.perm_code for r in perm_result.fetchall()]


async def get_user_role_code(db: AsyncSession, user_id) -> str | None:
    from app.models.user import Role, User

    result = await db.execute(
        select(Role.role_code)
        .join(User, User.role_id == Role.id)
        .where(User.id == user_id, User.is_deleted.is_(False), Role.is_deleted.is_(False))
    )
    row = result.first()
    return row[0] if row else None
