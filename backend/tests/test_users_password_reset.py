"""用户重名与管理员重设密码的接口级用例。

需要真实 Postgres（client/db fixture 会 probe，连不上整文件 skip）：
- 活跃/软删除同名用户创建 -> 409，且不会自动恢复软删除记录；
- 并发唯一约束冲突兜底 -> 409；
- admin 重设密码成功、非 admin（即使有 user:edit）403、目标不存在/已删除 404；
- 新旧密码登录行为、旧 JWT 失效；
- 审计落库请求体脱敏且包含 user_password_reset 动作。
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token
from app.models.audit import OperationLog
from app.models.user import User

pytestmark = pytest.mark.anyio

ADMIN_CREDENTIALS = {"username": "admin", "password": "admin123"}
NEW_PASSWORD = "NewPassw0rd!"


async def _login(client, username: str, password: str):
    return await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


async def _admin_headers(client):
    resp = await _login(client, **ADMIN_CREDENTIALS)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _admin_role_id(client, headers) -> str:
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 200, resp.text
    admin = next(u for u in resp.json()["data"]["list"] if u["username"] == "admin")
    return admin["role_id"]


async def _create_user(client, headers, username: str, password: str = "Passw0rd!") -> dict:
    resp = await client.post(
        "/api/v1/users",
        json={
            "username": username,
            "password": password,
            "role_id": await _admin_role_id(client, headers),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_duplicate_active_username_returns_409(client):
    headers = await _admin_headers(client)
    await _create_user(client, headers, "dup-active")

    resp = await client.post(
        "/api/v1/users",
        json={
            "username": "dup-active",
            "password": "OtherPassw0rd!",
            "role_id": await _admin_role_id(client, headers),
        },
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == 40901
    assert "用户名" in detail["msg"]


async def test_create_duplicate_soft_deleted_username_returns_409(client, db):
    headers = await _admin_headers(client)
    created = await _create_user(client, headers, "dup-deleted")

    deleted = await client.delete(f"/api/v1/users/{created['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    resp = await client.post(
        "/api/v1/users",
        json={
            "username": "dup-deleted",
            "password": "OtherPassw0rd!",
            "role_id": await _admin_role_id(client, headers),
        },
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == 40901

    # 不得自动恢复：原记录仍是软删除状态，列表里也看不到。
    rows = await db.execute(select(User).where(User.username == "dup-deleted"))
    users = rows.scalars().all()
    assert len(users) == 1
    assert users[0].is_deleted is True

    listing = await client.get("/api/v1/users", headers=headers)
    assert "dup-deleted" not in {u["username"] for u in listing.json()["data"]["list"]}


async def test_create_concurrent_unique_violation_returns_409(client, _sessionmaker):
    """预检查漏掉并发插入时，唯一约束异常必须兜底成 409 而不是 500。"""
    from app.core.database import get_db
    from app.main import app

    headers = await _admin_headers(client)
    role_id = await _admin_role_id(client, headers)

    class _ConflictOnCommit:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        async def commit(self):
            raise IntegrityError("INSERT INTO user", {}, Exception("duplicate key value"))

    async def _override_get_db():
        async with _sessionmaker() as session:
            yield _ConflictOnCommit(session)

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = _override_get_db
    try:
        resp = await client.post(
            "/api/v1/users",
            json={
                "username": "race-winner",
                "password": "Passw0rd!",
                "role_id": role_id,
            },
            headers=headers,
        )
    finally:
        app.dependency_overrides[get_db] = previous

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == 40901


async def test_admin_can_reset_password_and_old_token_is_revoked(client):
    headers = await _admin_headers(client)
    target = await _create_user(client, headers, "reset-target", password="OldPassw0rd!")

    old_login = await _login(client, "reset-target", "OldPassw0rd!")
    assert old_login.status_code == 200, old_login.text
    old_token = old_login.json()["data"]["access_token"]

    resp = await client.post(
        f"/api/v1/users/{target['id']}/reset-password",
        json={"new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    dumped = str(body)
    assert NEW_PASSWORD not in dumped
    assert "password_hash" not in dumped

    # 新密码可登录，旧密码不可登录。
    assert (await _login(client, "reset-target", NEW_PASSWORD)).status_code == 200
    assert (await _login(client, "reset-target", "OldPassw0rd!")).status_code == 401

    # 重设前签发的 JWT 立即失效（token_version 已自增）。
    revoked = await client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert revoked.status_code == 401, revoked.text
    assert revoked.json()["detail"]["code"] == 40104


async def test_reset_password_requires_admin_even_with_user_edit(client):
    headers = await _admin_headers(client)
    target = await _create_user(client, headers, "non-admin-editor")

    token = create_access_token(
        {
            "sub": target["id"],
            "role_code": "sales",
            "perms": ["user:edit"],
        }
    )
    resp = await client.post(
        f"/api/v1/users/{target['id']}/reset-password",
        json={"new_password": NEW_PASSWORD},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == 40301


async def test_reset_password_404_for_missing_or_soft_deleted_user(client):
    headers = await _admin_headers(client)

    missing = await client.post(
        f"/api/v1/users/{uuid4()}/reset-password",
        json={"new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert missing.status_code == 404, missing.text

    created = await _create_user(client, headers, "reset-deleted")
    await client.delete(f"/api/v1/users/{created['id']}", headers=headers)

    deleted = await client.post(
        f"/api/v1/users/{created['id']}/reset-password",
        json={"new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert deleted.status_code == 404, deleted.text


async def test_reset_password_audit_is_redacted(client, db):
    headers = await _admin_headers(client)
    target = await _create_user(client, headers, "audit-target")

    resp = await client.post(
        f"/api/v1/users/{target['id']}/reset-password",
        json={"new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    result = await db.execute(
        select(OperationLog)
        .where(OperationLog.action == "user_password_reset")
        .order_by(OperationLog.operate_time.desc())
    )
    log = result.scalars().first()
    assert log is not None, "重设密码必须落 user_password_reset 审计"
    assert log.module == "users"
    assert str(log.target_id) == target["id"]
    assert log.request_body == "[redacted]"
    assert NEW_PASSWORD not in " ".join(
        str(value) for value in (log.request_body, log.action, log.module, log.username)
    )


async def test_reset_password_enforces_length(client):
    headers = await _admin_headers(client)
    target = await _create_user(client, headers, "short-password-target")

    resp = await client.post(
        f"/api/v1/users/{target['id']}/reset-password",
        json={"new_password": "short"},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
