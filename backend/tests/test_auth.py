from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.user import User

pytestmark = pytest.mark.anyio


async def test_login_bad_credentials_returns_401(client):
    resp = await client.post("/api/v1/auth/login", json={"username": "alice", "password": "bad"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["code"] == 40101


async def test_login_response_contract_200_or_401(client):
    resp = await client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        body = resp.json()
        assert body["code"] == 200
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        assert body["data"]["token_type"] == "bearer"


async def test_protected_products_no_token_is_401(client):
    resp = await client.get("/api/v1/products")
    assert resp.status_code == 401


async def test_refresh_bad_token_is_401(client):
    resp = await client.post("/api/v1/auth/refresh?refresh_token=invalid.token.value")
    assert resp.status_code == 401


async def test_refresh_missing_token_is_422(client):
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code in (422, 401)


async def test_login_includes_role_code_and_perms_in_payload_if_200(client):
    resp = await client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
    if resp.status_code == 200:
        body = resp.json()
        token = body["data"]["access_token"]
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # jwt 3 parts


# --- 「最后登录」接口级用例 -------------------------------------------------------
# 这一段要一个可连的 Postgres 测试库：client / db fixture 会先 probe，连不上就整段
# skip（显示 skipped 不是 passed）。同样几条不变量里不依赖 DB 的部分放在
# tests/unit/test_last_login_time.py，那些在任何环境都会真的跑起来。

ADMIN_CREDENTIALS = {"username": "admin", "password": "admin123"}


async def _login_as_admin(client):
    resp = await client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _stored_last_login(db, username: str = "admin"):
    """查列而不是查实体：同一 session 里第二次查实体拿的是身份映射里的旧对象，读不到新值。"""
    result = await db.execute(select(User.last_login_time).where(User.username == username))
    return result.scalar_one()


async def _user_row(client, headers, username: str) -> dict:
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]["list"]
    row = next((item for item in rows if item["username"] == username), None)
    assert row is not None, f"用户列表里没有 {username}：{[item['username'] for item in rows]}"
    return row


async def test_login_persists_last_login_time(client, db):
    assert await _stored_last_login(db) is None, "种子 admin 还没登录过，字段应为空"

    before = datetime.now(UTC)
    await _login_as_admin(client)
    after = datetime.now(UTC)

    stamped = await _stored_last_login(db)
    assert stamped is not None, "登录成功却没落库，用户管理里的「最后登录」就是空壳"
    assert stamped.tzinfo is not None, "列是 timestamptz，取回来必须带时区"
    assert before <= stamped <= after


async def test_failed_login_does_not_touch_last_login_time(client, db):
    assert await _stored_last_login(db) is None

    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert resp.status_code == 401

    assert await _stored_last_login(db) is None, "撞一次密码就刷新最后登录时间，这一列就没意义了"


async def test_user_list_exposes_last_login_time(client):
    headers = await _login_as_admin(client)

    admin_row = await _user_row(client, headers, "admin")

    assert "last_login_time" in admin_row, "列表出参必须带这个字段"
    assert admin_row["last_login_time"] is not None, "刚登录过，列表里不该还是 null"
    assert datetime.fromisoformat(admin_row["last_login_time"]) <= datetime.now(UTC)


async def test_user_list_reports_null_for_a_user_that_never_logged_in(client):
    headers = await _login_as_admin(client)
    admin_row = await _user_row(client, headers, "admin")

    created = await client.post(
        "/api/v1/users",
        json={
            "username": "never-logged-in",
            "password": "Passw0rd!",
            "role_id": admin_row["role_id"],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["last_login_time"] is None

    fresh = await _user_row(client, headers, "never-logged-in")
    assert "last_login_time" in fresh, "字段不能被裁掉，前端靠 null 显示「从未」"
    assert fresh["last_login_time"] is None


async def test_login_still_succeeds_when_the_stamp_cannot_be_written(client, db, _sessionmaker):
    """落库失败只降级成 warning（app/api/v1/auth.py:78），不能把已通过校验的登录顶成 500。"""
    from app.core.database import get_db
    from app.main import app

    class _CommitFails:
        """只让 commit 炸，其余调用转发给真 session。"""

        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        async def commit(self):
            raise RuntimeError("模拟 last_login_time 落库失败")

    async def _override_get_db():
        async with _sessionmaker() as session:
            yield _CommitFails(session)

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = _override_get_db
    try:
        resp = await client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    finally:
        app.dependency_overrides[get_db] = previous

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["access_token"]
    assert await _stored_last_login(db) is None, "commit 失败后不该留下半条脏数据"
