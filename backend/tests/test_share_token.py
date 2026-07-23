import uuid
from datetime import UTC

import pytest
from sqlalchemy import select

from app.api.v1.share_token import _create_share_content_url
from app.core.security import decode_access_token
from app.models.audit import OperationLog, Share, ShareLog, ShareToken
from app.models.user import User

pytestmark = pytest.mark.anyio


def test_share_content_url_uses_backend_proxy():
    attachment_id = uuid.uuid4()

    url = _create_share_content_url(attachment_id)

    assert url.startswith(f"/api/v1/files/{attachment_id}/content?token=")
    assert "minio" not in url
    token = url.split("token=", 1)[1]
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["scope"] == "file_content"
    assert payload["attachment_id"] == str(attachment_id)


async def _seed_admin_user_id(session):
    """复用测试库已 seed 的 admin；无则取首个用户作为 creator。"""
    user = (
        await session.execute(select(User).where(User.username == "admin"))
    ).scalar_one_or_none()
    if user is None:
        user = (await session.execute(select(User).limit(1))).scalar_one_or_none()
    assert user is not None, "test DB not seeded with any user"
    return user.id


async def _make_share_and_token(
    session, *, status="active", expire_time=None, max_access_count=None, password=None
):
    """直接落库 Share + ShareToken，返回 token 字符串。"""
    creator_id = await _seed_admin_user_id(session)
    share = Share(
        share_type="proposal",
        target_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        creator_id=creator_id,
        status="active",
    )
    session.add(share)
    await session.flush()
    token = f"test_{uuid.uuid4().hex}"
    st = ShareToken(
        share_id=share.id,
        token=token,
        status=status,
        expire_time=expire_time,
        max_access_count=max_access_count,
        password=password,
        current_access_count=0,
    )
    session.add(st)
    await session.flush()
    return token


async def test_share_access_success_writes_both_logs(client, _sessionmaker):
    async with _sessionmaker() as s:
        token = await _make_share_and_token(s)
        await s.commit()

    resp = await client.get(
        f"/api/v1/share/{token}",
        headers={"X-Device-Fingerprint": "fp_success"},
    )
    assert resp.status_code == 200

    async with _sessionmaker() as s:
        sl = (
            (await s.execute(select(ShareLog).where(ShareLog.access_result == "success")))
            .scalars()
            .all()
        )
        assert any(log.visitor_ip is not None for log in sl)
        op = (
            (await s.execute(select(OperationLog).where(OperationLog.action == "share_access")))
            .scalars()
            .all()
        )
        assert len(op) == 1
        assert op[0].response_code == 200


async def test_share_access_unknown_token_404_denied_no_share_log(client, _sessionmaker):
    resp = await client.get("/api/v1/share/does_not_exist_token_xyz")
    assert resp.status_code == 404

    async with _sessionmaker() as s:
        # 不存在 token：无 ShareToken FK，不得写无效 share_log
        sl = (await s.execute(select(ShareLog))).scalars().all()
        assert len(sl) == 0
        # 但应作为安全事件记入 operation_log（仅记 action，不存原始 token）
        op = (
            (
                await s.execute(
                    select(OperationLog).where(OperationLog.action == "share_access_denied")
                )
            )
            .scalars()
            .all()
        )
        assert len(op) == 1
        assert op[0].response_code == 404


async def test_share_access_disabled_is_denied(client, _sessionmaker):
    async with _sessionmaker() as s:
        token = await _make_share_and_token(s, status="disabled")
        await s.commit()

    resp = await client.get(f"/api/v1/share/{token}")
    assert resp.status_code == 403

    async with _sessionmaker() as s:
        sl = (
            (await s.execute(select(ShareLog).where(ShareLog.access_result == "denied_expired")))
            .scalars()
            .all()
        )
        assert len(sl) >= 1
        op = (
            (
                await s.execute(
                    select(OperationLog).where(OperationLog.action == "share_access_denied")
                )
            )
            .scalars()
            .all()
        )
        assert len(op) == 1


async def test_share_access_expired_is_denied(client, _sessionmaker):
    from datetime import datetime, timedelta

    async with _sessionmaker() as s:
        past = datetime.now(UTC) - timedelta(days=1)
        token = await _make_share_and_token(s, expire_time=past)
        await s.commit()

    resp = await client.get(f"/api/v1/share/{token}")
    assert resp.status_code == 403

    async with _sessionmaker() as s:
        op = (
            (
                await s.execute(
                    select(OperationLog).where(OperationLog.action == "share_access_denied")
                )
            )
            .scalars()
            .all()
        )
        assert len(op) == 1


async def test_share_access_count_exhausted_is_denied(client, _sessionmaker):
    async with _sessionmaker() as s:
        token = await _make_share_and_token(s, max_access_count=0)
        await s.commit()

    resp = await client.get(f"/api/v1/share/{token}")
    assert resp.status_code == 403

    async with _sessionmaker() as s:
        sl = (
            (await s.execute(select(ShareLog).where(ShareLog.access_result == "denied_count")))
            .scalars()
            .all()
        )
        assert len(sl) >= 1
        op = (
            (
                await s.execute(
                    select(OperationLog).where(OperationLog.action == "share_access_denied")
                )
            )
            .scalars()
            .all()
        )
        assert len(op) == 1


async def test_share_access_wrong_password_is_denied(client, _sessionmaker):
    async with _sessionmaker() as s:
        token = await _make_share_and_token(s, password="secret")
        await s.commit()

    resp = await client.get(
        f"/api/v1/share/{token}",
    )
    assert resp.status_code == 403

    async with _sessionmaker() as s:
        sl = (
            (await s.execute(select(ShareLog).where(ShareLog.access_result == "denied_password")))
            .scalars()
            .all()
        )
        assert len(sl) >= 1
        op = (
            (
                await s.execute(
                    select(OperationLog).where(OperationLog.action == "share_access_denied")
                )
            )
            .scalars()
            .all()
        )
        assert len(op) == 1


async def test_share_access_correct_password_succeeds(client, _sessionmaker):
    async with _sessionmaker() as s:
        token = await _make_share_and_token(s, password="secret")
        await s.commit()

    resp = await client.get(f"/api/v1/share/{token}?password=secret")
    assert resp.status_code == 200

    async with _sessionmaker() as s:
        op = (
            (await s.execute(select(OperationLog).where(OperationLog.action == "share_access")))
            .scalars()
            .all()
        )
        assert len(op) == 1
