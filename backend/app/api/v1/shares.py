from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.audit import Share, ShareToken

router = APIRouter()


@router.post(
    "",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("share:create"))],
)
@audit_action("share_create", module="shares", target_id_kwarg="share_id")
async def create_share(request: Request, share_data: dict, db: AsyncSession = Depends(get_db)):
    share = Share(
        share_type=share_data["share_type"],
        target_id=share_data["target_id"],
        creator_id=share_data["creator_id"],
    )
    db.add(share)
    await db.flush()

    token_str = f"tk_{uuid4().hex[:12]}"
    expire_time = None
    if share_data.get("expire_hours"):
        expire_time = datetime.now(UTC) + timedelta(hours=share_data["expire_hours"])

    share_token = ShareToken(
        share_id=share.id,
        token=token_str,
        password=share_data.get("password"),
        expire_time=expire_time,
        max_access_count=share_data.get("max_access_count"),
    )
    db.add(share_token)
    await db.commit()

    return {
        "code": 200,
        "data": {
            "share_id": str(share.id),
            "share_url": f"/share/{token_str}",
            "token": token_str,
            "expire_time": expire_time.isoformat() if expire_time else None,
            "max_access_count": share_data.get("max_access_count"),
        },
    }


@router.get("", response_model=dict, dependencies=[Depends(PermissionChecker("share:view"))])
async def list_shares(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Share).where(Share.is_deleted.is_(False)))
    shares = result.scalars().all()
    return {
        "code": 200,
        "data": {
            "list": [
                {
                    "id": str(s.id),
                    "share_type": s.share_type,
                    "target_id": str(s.target_id),
                    "creator_id": str(s.creator_id),
                    "status": s.status,
                    "create_time": s.create_time.isoformat() if s.create_time else None,
                }
                for s in shares
            ]
        },
    }


@router.delete("/{share_id}", dependencies=[Depends(PermissionChecker("share:delete"))])
@audit_action("share_revoke", module="shares")
async def revoke_share(request: Request, share_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Share).where(Share.id == share_id, Share.is_deleted.is_(False))
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "分享不存在"})

    share.is_deleted = True
    share.status = "disabled"
    await db.execute(
        sa_update(ShareToken)
        .where(ShareToken.share_id == share_id, ShareToken.is_deleted.is_(False))
        .values(status="disabled")
    )
    await db.commit()
    return {"code": 200, "msg": "success"}
