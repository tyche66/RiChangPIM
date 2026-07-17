"""ShareToken 过期定时扫描（docs/03 §5.2 / §8.2）。

将 ``status='active' AND expire_time < now()`` 的凭证批量标记为 ``expired``，
返回被扫出的记录数。设计为可被独立 cron 脚本或应用层定时器直接调用。
"""

from sqlalchemy import func
from sqlalchemy import update as sa_update

from app.core.database import AsyncSessionLocal
from app.models.audit import ShareToken


async def sweep_expired_tokens(db=None) -> int:
    """扫描并标记过期的 ShareToken。

    Args:
        db: 可选外部 ``AsyncSession``；为 ``None`` 时内部自建 session 并关闭。

    Returns:
        被标记为 ``expired`` 的记录数（``swept_count``）。
    """
    own_session = db is None
    if own_session:
        db = AsyncSessionLocal()

    try:
        result = await db.execute(
            sa_update(ShareToken)
            .where(
                ShareToken.status == "active",
                ShareToken.expire_time.is_not(None),
                ShareToken.expire_time < func.now(),
                ShareToken.is_deleted.is_(False),
            )
            .values(status="expired")
        )
        swept = result.rowcount or 0
        await db.commit()
        return swept
    finally:
        if own_session:
            await db.close()
