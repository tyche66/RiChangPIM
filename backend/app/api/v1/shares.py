import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker, get_current_user
from app.core.security import ensure_bcrypt_compatible, get_password_hash
from app.middleware.audit import audit_action
from app.models.audit import Share, ShareToken
from app.models.sales import Proposal, Quotation
from app.services.system_setting import get_share_defaults

router = APIRouter()

MAX_EXPIRE_HOURS = 720  # 30 days
MAX_ACCESS_COUNT = 10000
# FR-3：缺省统一为 24 小时；未显式传参时读全局设置（system_setting.share），
# 这两个常量只作为设置项同名默认值的镜像说明，不再直接参与业务分支。
DEFAULT_EXPIRE_HOURS = 24
DEFAULT_MAX_ACCESS_COUNT = 100

SHARE_TYPES = {"proposal", "quotation"}


class ShareCreate(BaseModel):
    share_type: str = Field("proposal", pattern="^(proposal|quotation)$")
    target_id: UUID
    # 未传时读全局设置缺省值（见 create_share），因此 Schema 默认 None。
    expire_hours: int | None = Field(None, ge=1, le=MAX_EXPIRE_HOURS)
    max_access_count: int | None = Field(None, ge=1, le=MAX_ACCESS_COUNT)
    password: str | None = Field(None, min_length=8, max_length=72)

    @field_validator("password", mode="before")
    @classmethod
    def _empty_password_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("password")
    @classmethod
    def _password_bytes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_bcrypt_compatible(value)


@router.post(
    "",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("share:create"))],
)
@audit_action("share_create", module="shares", target_id_kwarg="share_id")
async def create_share(
    request: Request,
    share_data: ShareCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # creator_id 必须从登录态令牌中获取，禁止信任客户端传入。
    try:
        creator_id = UUID(current_user["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=401, detail={"code": 40103, "msg": "当前用户身份无效"}
        ) from None

    # 未显式传参时读全局设置的缺省值（FR-3：默认从 168h 收敛为 24h，
    # 直接调接口且不传 expire_hours 的调用方需知悉该行为变化）。
    # 必须放在所有写操作之前：设置行缺失时服务层会 commit 默认行，
    # 若此时事务里已有未提交的 share INSERT 会被一起带出去。
    share_defaults = await get_share_defaults(db)

    # 验证 target 真实未删除
    if share_data.share_type == "proposal":
        target = (
            await db.execute(
                select(Proposal).where(
                    Proposal.id == share_data.target_id, Proposal.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if not target:
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": "方案不存在或已删除"}
            )
        # proposal 草稿允许分享
        if target.status not in ("draft", "confirmed"):
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "方案未确认，不可分享"}
            )
    elif share_data.share_type == "quotation":
        target = (
            await db.execute(
                select(Quotation).where(
                    Quotation.id == share_data.target_id, Quotation.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if not target:
            raise HTTPException(
                status_code=404, detail={"code": 40401, "msg": "报价单不存在或已删除"}
            )
        # 仅 confirmed quotation 可分享
        if target.status != "confirmed":
            raise HTTPException(
                status_code=422, detail={"code": 42201, "msg": "报价单未确认，不可分享"}
            )
    else:
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "share_type 非法"}
        )

    share = Share(
        share_type=share_data.share_type,
        target_id=share_data.target_id,
        creator_id=creator_id,
    )
    db.add(share)
    await db.flush()

    token_str = f"tk_{secrets.token_urlsafe(32)}"
    expire_hours = (
        share_data.expire_hours
        if share_data.expire_hours is not None
        else share_defaults.share_default_expire_hours
    )
    max_access_count = (
        share_data.max_access_count
        if share_data.max_access_count is not None
        else share_defaults.share_default_max_access_count
    )
    expire_time = datetime.now(UTC) + timedelta(hours=expire_hours)
    password_hash = (
        get_password_hash(share_data.password) if share_data.password else None
    )

    share_token = ShareToken(
        share_id=share.id,
        token=token_str,
        password=password_hash,
        password_hash=password_hash,
        expire_time=expire_time,
        max_access_count=max_access_count,
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
            "max_access_count": max_access_count,
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


@router.get(
    "/target/{share_type}/{target_id}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("share:view"))],
)
async def get_share_by_target(
    share_type: str,
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """按业务对象读取最近一次分享，供方案/报价详情页复用链接与二维码。

    只返回当前登录用户有 ``share:view`` 权限的数据；没有分享时返回 data=null，
    前端据此展示空态，不把它当成接口错误。
    """
    if share_type not in SHARE_TYPES:
        raise HTTPException(
            status_code=422, detail={"code": 42201, "msg": "share_type 非法"}
        )

    share = (
        await db.execute(
            select(Share)
            .where(
                Share.share_type == share_type,
                Share.target_id == target_id,
                Share.is_deleted.is_(False),
            )
            .order_by(Share.create_time.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if share is None:
        return {"code": 200, "data": None}

    token = (
        await db.execute(
            select(ShareToken)
            .where(
                ShareToken.share_id == share.id,
                ShareToken.is_deleted.is_(False),
            )
            .order_by(ShareToken.create_time.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if token is None:
        return {
            "code": 200,
            "data": {
                "share_id": str(share.id),
                "share_type": share.share_type,
                "target_id": str(share.target_id),
                "status": share.status,
                "share_url": None,
                "token": None,
                "expire_time": None,
                "max_access_count": None,
                "current_access_count": 0,
                "password_protected": False,
            },
        }

    return {
        "code": 200,
        "data": {
            "share_id": str(share.id),
            "share_type": share.share_type,
            "target_id": str(share.target_id),
            "status": share.status,
            "share_url": f"/share/{token.token}",
            "token": token.token,
            "expire_time": token.expire_time.isoformat() if token.expire_time else None,
            "max_access_count": token.max_access_count,
            "current_access_count": token.current_access_count or 0,
            "password_protected": bool(token.password_hash),
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
