from datetime import UTC, datetime, timedelta
from functools import partial
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import create_access_token
from app.core.serializers import filter_sensitive_fields
from app.middleware.audit import audit_action
from app.models.audit import Share, ShareLog, ShareToken, Visitor
from app.models.product import Attachment, Product, ProductImage, SceneImage, product_scene_image
from app.models.sales import ProjectSpace, Proposal, ProposalItem, Quotation, QuotationItem
from app.services.proposal_floor_plans import (
    content_url as floor_plan_content_url,
)
from app.services.proposal_floor_plans import (
    load_floor_plans,
)

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None
    client = request.client
    if client:
        return client.host
    return None


def _normalize_expire(exp: datetime | None) -> datetime | None:
    if exp is None:
        return None
    if exp.tzinfo is None:
        return exp.replace(tzinfo=UTC)
    return exp.astimezone(UTC)


async def _write_share_log(
    db: AsyncSession,
    *,
    token_id: UUID | None,
    visitor_id: UUID | None,
    ip: str | None,
    ua: str | None,
    fingerprint: str | None,
    openid: str | None,
    access_result: str,
) -> None:
    log = ShareLog(
        share_token_id=token_id,
        visitor_id=visitor_id,
        visitor_ip=ip,
        visitor_ua=ua,
        device_fingerprint=fingerprint,
        openid=openid,
        access_result=access_result,
    )
    db.add(log)
    await db.commit()


async def _resolve_visitor(
    db: AsyncSession,
    *,
    fingerprint: str | None,
    openid: str | None,
) -> Visitor:
    visitor: Visitor | None = None
    if openid:
        visitor = (
            await db.execute(select(Visitor).where(Visitor.openid == openid))
        ).scalar_one_or_none()
    elif fingerprint:
        visitor = (
            await db.execute(select(Visitor).where(Visitor.fingerprint == fingerprint))
        ).scalar_one_or_none()

    if visitor is not None:
        visitor.last_seen_time = datetime.now(UTC)
        return visitor

    visitor = Visitor(fingerprint=fingerprint, openid=openid)
    db.add(visitor)
    await db.flush()
    return visitor


def _create_share_content_url(attachment_id: UUID) -> str:
    """为匿名分享页生成经后端代理的短时图片访问地址。"""
    token = create_access_token(
        {
            "sub": "share-content",
            "scope": "file_content",
            "attachment_id": str(attachment_id),
        },
        expires_delta=timedelta(minutes=15),
    )
    return f"/api/v1/files/{attachment_id}/content?token={token}"


def _snapshot_field(snapshot: dict | None, product, key: str):
    """展示字段取值：快照优先，其次当前产品，最后 None。"""
    value = (snapshot or {}).get(key)
    if value in (None, "", []):
        value = getattr(product, key, None)
    return value


def _space_labels(item) -> tuple[str | None, str | None]:
    """Return saved labels, echoing an existing bound space for legacy rows."""
    floor_label = item.floor_label
    space_label = item.space_label
    bound_space = item.__dict__.get("space")
    if bound_space is None:
        return floor_label, space_label
    if floor_label is None:
        if bound_space.space_type == "floor":
            floor_label = bound_space.space_name
        else:
            parent = getattr(bound_space, "parent", None)
            if parent is not None and parent.space_type == "floor":
                floor_label = parent.space_name
    if space_label is None and bound_space.space_type != "floor":
        space_label = bound_space.space_name
    return floor_label, space_label



async def _fetch_content_urls(
    db: AsyncSession, attachment_ids: list[UUID]
) -> dict[UUID, str]:
    """为有效附件生成经后端代理的访问地址。"""
    if not attachment_ids:
        return {}

    result = await db.execute(
        select(Attachment.id, Attachment.oss_key)
        .where(Attachment.id.in_(attachment_ids), Attachment.is_deleted.is_(False))
    )
    rows = result.fetchall()
    if not rows:
        return {}

    url_map: dict[UUID, str] = {}
    for att_id, _ in rows:
        url_map[att_id] = _create_share_content_url(att_id)
    return url_map


async def _build_content(db: AsyncSession, share_type: str, target_id: UUID) -> dict | None:

    if share_type == "proposal":
        prop = (
            await db.execute(
                select(Proposal).where(Proposal.id == target_id, Proposal.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if prop is None:
            return None
        rows = (
            (
                await db.execute(
                    select(ProposalItem)
                    .options(selectinload(ProposalItem.space).selectinload(ProjectSpace.parent))
                    .where(ProposalItem.proposal_id == prop.id)
                )
            )
            .scalars()
            .all()
        )
        # Track D：平面图与商品明细数量无关，没有明细的分享也要能展示平面图。
        # 地址走 15 分钟短 token，匿名访客拿不到 MinIO 地址。
        floor_plans = [
            {
                "id": str(fp.id),
                "name": fp.name,
                "floor_label": fp.floor_label,
                "space_label": fp.space_label,
                "sort": fp.sort,
                "image_url": floor_plan_content_url(fp.attachment_id),
            }
            for fp in await load_floor_plans(db, prop.id)
        ]
        product_ids = [it.product_id for it in rows]
        if not product_ids:
            return {
                "proposal_no": prop.proposal_no,
                "proposal_name": prop.proposal_name,
                "customer_name": prop.customer_name,
                "status": prop.status,
                "total_face_value": 0.0,
                "floor_plans": floor_plans,
                "items": [],
            }

        # 批量加载产品
        prod_result = await db.execute(
            select(Product)
                .options(selectinload(Product.category))
                .where(Product.id.in_(product_ids), Product.is_deleted.is_(False))
        )
        products_map = {p.id: p for p in prod_result.scalars().all()}

        # 批量加载产品图片
        img_result = await db.execute(
            select(ProductImage)
            .where(ProductImage.product_id.in_(product_ids), ProductImage.is_deleted.is_(False))
        )
        product_images: dict[UUID, list[ProductImage]] = {}
        for pi in img_result.scalars().all():
            product_images.setdefault(pi.product_id, []).append(pi)

        # 批量加载场景图关联
        scene_assoc = await db.execute(
            select(
            product_scene_image.c.product_id,
            product_scene_image.c.scene_image_id,
            product_scene_image.c.sort,
        )
        .where(
            product_scene_image.c.product_id.in_(product_ids),
            product_scene_image.c.is_deleted.is_(False),
        )
        .order_by(product_scene_image.c.product_id, product_scene_image.c.sort)
        )
        scene_assoc_rows = scene_assoc.fetchall()
        scene_image_ids = [row.scene_image_id for row in scene_assoc_rows]

        # 批量加载场景图详情
        scene_images_map: dict[UUID, list[SceneImage]] = {}
        if scene_image_ids:
            scene_result = await db.execute(
                select(SceneImage)
                .where(SceneImage.id.in_(scene_image_ids), SceneImage.is_deleted.is_(False))
            )
            for si in scene_result.scalars().all():
                scene_images_map.setdefault(si.id, []).append(si)

        # 构建场景图按 product_id 分组的字典（含 attachment_id）
        product_scene_images: dict[UUID, list[dict]] = {}
        for row in scene_assoc_rows:
            pid = row.product_id
            sid = row.scene_image_id
            sort = row.sort or 0
            scenes = scene_images_map.get(sid, [])
            if scenes:
                si = scenes[0]
                product_scene_images.setdefault(pid, []).append(
                    {
                        "id": str(si.id),
                        "name": si.name,
                        "sort": sort,
                        "attachment_id": si.attachment_id,
                    }
                )

        # 收集所有需要预签名的 attachment_id
        cover_att_ids: list[UUID] = []
        scene_att_ids: list[UUID] = []
        for pid in product_ids:
            images = product_images.get(pid, [])
            if images:
                cover = next((img for img in images if img.is_cover), None) or images[0]
                if cover and cover.attachment_id:
                    cover_att_ids.append(cover.attachment_id)
            for si_info in product_scene_images.get(pid, []):
                if si_info["attachment_id"]:
                    scene_att_ids.append(si_info["attachment_id"])

        all_att_ids = list(dict.fromkeys(cover_att_ids + scene_att_ids))
        url_map = await _fetch_content_urls(db, all_att_ids)

        items = []
        total_face_value = 0.0
        for it in rows:
            prod = products_map.get(it.product_id)
            images = product_images.get(it.product_id, [])
            cover = (
                next((img for img in images if img.is_cover), None)
                or (images[0] if images else None)
            )

            cover_image_url = None
            if cover and cover.attachment_id:
                cover_image_url = url_map.get(cover.attachment_id)

            scenes = []
            for si_info in product_scene_images.get(it.product_id, [])[:30]:
                img_url = url_map.get(si_info["attachment_id"])
                scenes.append(
                    {
                        "id": si_info["id"],
                        "name": si_info["name"],
                        "image_url": img_url,
                        "sort": si_info["sort"],
                    }
                )

            snapshot = it.product_snapshot
            snapshot_face_price = (snapshot or {}).get("face_price")
            face_price = (
                snapshot_face_price
                if snapshot_face_price not in (None, "")
                else (prod.face_price if prod else None)
            )
            line_total = round(face_price * it.quantity, 2) if face_price is not None else 0.0
            total_face_value += line_total

            # 展示事实按"快照优先、当前产品其次"合并，保证历史方案不漂移
            _field = partial(_snapshot_field, snapshot, prod)
            floor_label, space_label = _space_labels(it)

            items.append(
                {
                    "product_id": str(it.product_id),
                    "product_no": _field("product_no"),
                    "product_name": _field("product_name"),
                    "category_name": _field("category_name")
                    or (prod.category.category_name if prod and prod.category else None),
                    "face_price": face_price,
                    "quantity": it.quantity,
                    "line_total": line_total,
                    "cover_image_url": cover_image_url,
                    "scene_images": scenes,
                    # Track C：空间位置与产品事实快照
                    "project_space_id": (
                        str(it.project_space_id) if it.project_space_id else None
                    ),
                    "floor_label": floor_label,
                    "space_label": space_label,
                    "material_desc": it.material_desc,
                    "material": _field("material"),
                    "colors": _field("colors"),
                    "material_description": _field("material_description"),
                    "specification": _field("specification"),
                    "product_snapshot": snapshot or None,
                }
            )
        return {
            "proposal_no": prop.proposal_no,
            "proposal_name": prop.proposal_name,
            "customer_name": prop.customer_name,
            "status": prop.status,
            "total_face_value": round(total_face_value, 2),
            "floor_plans": floor_plans,
            "items": items,
        }

    if share_type == "quotation":
        quo = (
            await db.execute(
                select(Quotation).where(Quotation.id == target_id, Quotation.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if quo is None:
            return None
        rows = (
            (
                await db.execute(
                    select(QuotationItem)
                    .options(selectinload(QuotationItem.space).selectinload(ProjectSpace.parent))
                    .where(QuotationItem.quotation_id == quo.id)
                )
            )
            .scalars()
            .all()
        )
        product_ids = [it.product_id for it in rows]
        if not product_ids:
            return {
                "quotation_no": quo.quotation_no,
                "status": quo.status,
                "total_amount": quo.total_amount,
                "subtotal": quo.subtotal,
                "items": [],
            }

        # 批量加载产品
        prod_result = await db.execute(
            select(Product)
                .options(selectinload(Product.category))
                .where(Product.id.in_(product_ids), Product.is_deleted.is_(False))
        )
        products_map = {p.id: p for p in prod_result.scalars().all()}

        # 批量加载产品图片
        img_result = await db.execute(
            select(ProductImage)
            .where(ProductImage.product_id.in_(product_ids), ProductImage.is_deleted.is_(False))
        )
        product_images: dict[UUID, list[ProductImage]] = {}
        for pi in img_result.scalars().all():
            product_images.setdefault(pi.product_id, []).append(pi)

        # 批量加载场景图关联
        scene_assoc = await db.execute(
            select(
            product_scene_image.c.product_id,
            product_scene_image.c.scene_image_id,
            product_scene_image.c.sort,
        )
        .where(
            product_scene_image.c.product_id.in_(product_ids),
            product_scene_image.c.is_deleted.is_(False),
        )
        .order_by(product_scene_image.c.product_id, product_scene_image.c.sort)
        )
        scene_assoc_rows = scene_assoc.fetchall()
        scene_image_ids = [row.scene_image_id for row in scene_assoc_rows]

        # 批量加载场景图详情
        scene_images_map: dict[UUID, list[SceneImage]] = {}
        if scene_image_ids:
            scene_result = await db.execute(
                select(SceneImage)
                .where(SceneImage.id.in_(scene_image_ids), SceneImage.is_deleted.is_(False))
            )
            for si in scene_result.scalars().all():
                scene_images_map.setdefault(si.id, []).append(si)

        # 构建场景图按 product_id 分组的字典（含 attachment_id）
        product_scene_images: dict[UUID, list[dict]] = {}
        for row in scene_assoc_rows:
            pid = row.product_id
            sid = row.scene_image_id
            sort = row.sort or 0
            scenes = scene_images_map.get(sid, [])
            if scenes:
                si = scenes[0]
                product_scene_images.setdefault(pid, []).append(
                    {
                        "id": str(si.id),
                        "name": si.name,
                        "sort": sort,
                        "attachment_id": si.attachment_id,
                    }
                )

        # 收集所有需要预签名的 attachment_id
        cover_att_ids: list[UUID] = []
        scene_att_ids: list[UUID] = []
        for pid in product_ids:
            images = product_images.get(pid, [])
            if images:
                cover = next((img for img in images if img.is_cover), None) or images[0]
                if cover and cover.attachment_id:
                    cover_att_ids.append(cover.attachment_id)
            for si_info in product_scene_images.get(pid, []):
                if si_info["attachment_id"]:
                    scene_att_ids.append(si_info["attachment_id"])

        all_att_ids = list(dict.fromkeys(cover_att_ids + scene_att_ids))
        url_map = await _fetch_content_urls(db, all_att_ids)

        items = []
        for it in rows:
            prod = products_map.get(it.product_id)
            images = product_images.get(it.product_id, [])
            cover = (
                next((img for img in images if img.is_cover), None)
                or (images[0] if images else None)
            )

            cover_image_url = None
            if cover and cover.attachment_id:
                cover_image_url = url_map.get(cover.attachment_id)

            scenes = []
            for si_info in product_scene_images.get(it.product_id, [])[:30]:
                img_url = url_map.get(si_info["attachment_id"])
                scenes.append(
                    {
                        "id": si_info["id"],
                        "name": si_info["name"],
                        "image_url": img_url,
                        "sort": si_info["sort"],
                    }
                )

            subtotal = round(it.unit_price * it.quantity, 2)
            # 展示事实按"快照优先、当前产品其次"合并，保证历史报价不漂移
            snapshot = it.product_snapshot
            _field = partial(_snapshot_field, snapshot, prod)
            floor_label, space_label = _space_labels(it)

            items.append(
                {
                    "product_id": str(it.product_id),
                    "product_no": _field("product_no"),
                    "product_name": _field("product_name"),
                    "category_name": _field("category_name")
                    or (prod.category.category_name if prod and prod.category else None),
                    "face_price": prod.face_price if prod else None,
                    "quantity": it.quantity,
                    "unit_price": it.unit_price,
                    "tax_rate": it.tax_rate,
                    "subtotal": subtotal,
                    "cover_image_url": cover_image_url,
                    "scene_images": scenes,
                    # Track C：空间位置与产品事实快照
                    "project_space_id": (
                        str(it.project_space_id) if it.project_space_id else None
                    ),
                    "floor_label": floor_label,
                    "space_label": space_label,
                    "material_desc": it.material_desc,
                    "material": _field("material"),
                    "colors": _field("colors"),
                    "material_description": _field("material_description"),
                    "specification": _field("specification"),
                    "product_snapshot": snapshot or None,
                }
            )
        return {
            "quotation_no": quo.quotation_no,
            "status": quo.status,
            "total_amount": quo.total_amount,
            "subtotal": quo.subtotal,
            "items": items,
        }

    return None


# ---------------------------------------------------------------------------
# 公开接口（无需后台 JWT / RBAC）。
#
# 公开依据：C 端访客通过分享链接访问，天然没有后台账号，因此不能挂
# PermissionChecker / get_current_user；鉴权改由「分享令牌本身」承担。
# 审计与滥用保护：
#   - token 有效性 / status（active|disabled|expired）校验；
#   - expire_time 过期校验；
#   - max_access_count 访问次数上限（原子自增，超限 403）；
#   - 可选访问密码校验；
#   - 每次访问（成功/各类拒绝）均写 ShareLog（IP/UA/指纹/openid/结果），可追溯。
# 故本路由为唯一豁免后台鉴权的接口，其余阶段①②③接口均已接入 RBAC。
# ---------------------------------------------------------------------------
@router.get("/share/{token}")
@audit_action("share_access", module="shares", failed_action="share_access_denied")
async def get_share_content(
    request: Request,
    token: str,
    password: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    fingerprint = request.headers.get("x-device-fingerprint") or request.headers.get(
        "X-Device-Fingerprint"
    )
    openid = request.headers.get("x-openid") or request.headers.get("X-Openid")
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")

    result = await db.execute(
        select(ShareToken).where(ShareToken.token == token, ShareToken.is_deleted.is_(False))
    )
    st = result.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "分享不存在"})

    if st.status == "disabled":
        await _write_share_log(
            db,
            token_id=st.id,
            visitor_id=None,
            ip=ip,
            ua=ua,
            fingerprint=fingerprint,
            openid=openid,
            access_result="denied_expired",
        )
        raise HTTPException(status_code=403, detail={"code": 40301, "msg": "分享已失效"})
    if st.status == "expired":
        await _write_share_log(
            db,
            token_id=st.id,
            visitor_id=None,
            ip=ip,
            ua=ua,
            fingerprint=fingerprint,
            openid=openid,
            access_result="denied_expired",
        )
        raise HTTPException(status_code=403, detail={"code": 40302, "msg": "分享已过期"})

    now = datetime.now(UTC)
    exp = _normalize_expire(st.expire_time)
    if exp is not None and exp < now:
        await db.execute(
            sa_update(ShareToken)
            .where(ShareToken.id == st.id, ShareToken.status == "active")
            .values(status="expired")
        )
        await _write_share_log(
            db,
            token_id=st.id,
            visitor_id=None,
            ip=ip,
            ua=ua,
            fingerprint=fingerprint,
            openid=openid,
            access_result="denied_expired",
        )
        raise HTTPException(status_code=403, detail={"code": 40302, "msg": "分享已过期"})

    result = await db.execute(
        sa_update(ShareToken)
        .where(
            ShareToken.id == st.id,
            or_(
                ShareToken.max_access_count.is_(None),
                ShareToken.current_access_count < ShareToken.max_access_count,
            ),
        )
        .values(current_access_count=ShareToken.current_access_count + 1)
    )
    if result.rowcount == 0:
        await _write_share_log(
            db,
            token_id=st.id,
            visitor_id=None,
            ip=ip,
            ua=ua,
            fingerprint=fingerprint,
            openid=openid,
            access_result="denied_count",
        )
        raise HTTPException(status_code=403, detail={"code": 40303, "msg": "访问次数已用完"})

    if st.password is not None and st.password != password:
        await db.execute(
            sa_update(ShareToken)
            .where(ShareToken.id == st.id)
            .values(current_access_count=ShareToken.current_access_count - 1)
        )
        await _write_share_log(
            db,
            token_id=st.id,
            visitor_id=None,
            ip=ip,
            ua=ua,
            fingerprint=fingerprint,
            openid=openid,
            access_result="denied_password",
        )
        raise HTTPException(status_code=403, detail={"code": 40304, "msg": "访问密码错误"})

    share = (
        await db.execute(select(Share).where(Share.id == st.share_id, Share.is_deleted.is_(False)))
    ).scalar_one_or_none()
    if share is None:
        await _write_share_log(
            db,
            token_id=st.id,
            visitor_id=None,
            ip=ip,
            ua=ua,
            fingerprint=fingerprint,
            openid=openid,
            access_result="denied_expired",
        )
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "分享不存在"})

    visitor = await _resolve_visitor(db, fingerprint=fingerprint, openid=openid)

    raw_content = await _build_content(db, share.share_type, share.target_id)
    content = filter_sensitive_fields(raw_content, role_code="sales") if raw_content else None

    await _write_share_log(
        db,
        token_id=st.id,
        visitor_id=visitor.id,
        ip=ip,
        ua=ua,
        fingerprint=fingerprint,
        openid=openid,
        access_result="success",
    )

    return {
        "code": 200,
        "data": {
            "share_type": share.share_type,
            "target_id": str(share.target_id),
            "access_count": st.current_access_count + 1,
            "content": content,
        },
    }
