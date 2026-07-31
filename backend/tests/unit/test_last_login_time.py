"""「最后登录」这条链路上不依赖数据库的那几条不变量。

`tests/test_auth.py` 里的接口级用例要一个可连的 Postgres，没有服务时整文件 skip
（显示 skipped 不是 passed）。而下面这几条恰恰最容易悄悄退化，所以在单元层用假
session 直接调 endpoint 函数，任何环境都真的跑起来：

1. 登录成功必须把 `user.last_login_time` 盖成「现在」并且真的 commit
   （`app/api/v1/auth.py:76`），否则用户管理里的「最后登录」永远是空壳。
2. 登录失败（密码错 / 用户不存在）不许碰这个字段、也不许 commit —— 否则随便撞
   一次密码就能刷新别人的「最后登录」，这一列就不能再用来判断账号是否还在用。
3. 落库失败只降级成 warning：已经通过校验的登录不能被一次写库失败顶成 500。
4. 用户列表接口要带出这个字段，没登录过时是 `null` —— 前端
   `frontend/src/views/Users.vue` 靠 `null` 显示「从未」，字段被裁掉那一列就只剩空白。

本文件 import 了 `app.api.v1.auth`，它会连带 import `app.core.database`：引擎在
import 期只是被构造出来（`create_async_engine` 不连库），连接串由 `tests/conftest.py`
注入 dummy 值；唯一会真开 socket 的是审计落库，已由 `_no_audit_write` 桩掉。
所以这一层仍然不碰 DB。
"""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.auth import login
from app.api.v1.users import list_users
from app.core.security import get_password_hash
from app.middleware import audit as audit_module
from app.models.user import User
from app.schemas.user import LoginRequest, UserResponse

ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_hash() -> str:
    """bcrypt(rounds=12) 校验一次约 0.3s，整个模块只算这一个哈希。"""
    return get_password_hash(ADMIN_PASSWORD)


@pytest.fixture(autouse=True)
def _no_audit_write(monkeypatch):
    """桩掉审计落库。

    `@audit_action` 用的是独立 session（`app/middleware/audit.py`），不桩的话它会拿
    dummy 连接串真去连 localhost:5432。失败会被它自己的 try 吞掉（只留一条 ERROR
    日志，测试照样绿），但每条用例都白等一次 TCP 拒连，单元层也就不再是「不碰 DB」。
    """

    async def _skip_write(**_kwargs):
        return None

    monkeypatch.setattr(audit_module, "_write_operation_log", _skip_write)


def _http_request(body: bytes = b'{"username": "admin", "password": "***"}') -> Request:
    """真 Starlette Request：`@audit_action` 要读 headers / client / state 和 `body()`。"""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "raw_path": b"/api/v1/auth/login",
        "query_string": b"",
        "root_path": "",
        "scheme": "http",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 54321),
        "server": ("testserver", 80),
        "state": {},
    }

    async def _receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, _receive)


def _user(**overrides) -> User:
    """一条最小可用的 `user` 行；用真 ORM 对象，列名改了这些用例就该红。"""
    fields = {
        "id": uuid4(),
        "username": "admin",
        "password_hash": "$2b$12$this-is-not-a-real-bcrypt-hash",
        "email": None,
        "phone": None,
        "status": "active",
        "role_id": uuid4(),
        "last_login_time": None,
        # server_default 只在真的 INSERT 时生效，未落库的实例得自己填 create_time，
        # 否则 UserResponse 里这个必填字段会校验失败。
        "create_time": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return User(**fields)


class _FakeResult:
    """`db.execute()` 返回值的替身，只实现被测代码真正用到的取值方法。"""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value

    def first(self):
        return self._value

    def fetchall(self):
        return list(self._value or [])

    def scalars(self):
        return self

    def all(self):
        return list(self._value or [])


class _FakeSession:
    """按脚本回放 execute 结果的假 AsyncSession，并数清 commit / rollback 次数。"""

    def __init__(self, results, *, commit_error: Exception | None = None):
        self._results = list(results)
        self._commit_error = commit_error
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, *_args, **_kwargs):
        if not self._results:
            raise AssertionError("被测代码查库次数超出脚本，需要补 results")
        return _FakeResult(self._results.pop(0))

    async def commit(self):
        self.commits += 1
        if self._commit_error is not None:
            raise self._commit_error

    async def rollback(self):
        self.rollbacks += 1


def _login_script(user: User, role_code: str = "admin", perms=("user:view",)) -> list:
    """login() 依次要用到的三次 execute 结果：查用户 → 查角色 → 查权限。"""
    return [user, (user, role_code), [SimpleNamespace(perm_code=code) for code in perms]]


async def _login(session, password: str = ADMIN_PASSWORD):
    return await login(
        request=_http_request(),
        login_data=LoginRequest(username="admin", password=password),
        db=session,
    )


async def test_successful_login_stamps_last_login_time_and_commits(admin_hash):
    user = _user(password_hash=admin_hash)
    assert user.last_login_time is None
    session = _FakeSession(_login_script(user))

    before = datetime.now(UTC)
    body = await _login(session)
    after = datetime.now(UTC)

    assert body["code"] == 200
    assert body["data"]["access_token"]
    assert session.commits == 1, "只赋值不 commit 等于没写"
    assert session.rollbacks == 0

    stamped = user.last_login_time
    assert stamped is not None
    assert stamped.tzinfo is not None, "列是 timestamptz，落库的值必须带时区"
    assert before <= stamped <= after


@pytest.mark.parametrize(
    ("user_found", "password"),
    [(True, "wrong-password"), (False, ADMIN_PASSWORD)],
    ids=["wrong-password", "unknown-username"],
)
async def test_failed_login_never_stamps_last_login_time(admin_hash, user_found, password):
    stale = datetime(2026, 7, 1, 8, 30, tzinfo=UTC)
    user = _user(password_hash=admin_hash, last_login_time=stale)
    session = _FakeSession([user if user_found else None])

    with pytest.raises(HTTPException) as raised:
        await _login(session, password=password)

    assert raised.value.status_code == 401
    assert raised.value.detail["code"] == 40101
    assert user.last_login_time == stale, "撞一次密码就刷新最后登录时间，这一列就没意义了"
    assert session.commits == 0
    assert session.rollbacks == 0


async def test_login_survives_a_failed_last_login_write(admin_hash, caplog):
    session = _FakeSession(
        _login_script(_user(password_hash=admin_hash)),
        commit_error=RuntimeError("connection reset by peer"),
    )

    with caplog.at_level(logging.WARNING, logger="app.auth"):
        body = await _login(session)

    assert body["code"] == 200, "凭据是对的，落库失败不该把登录本身顶掉"
    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"]
    assert session.rollbacks == 1, "commit 失败必须 rollback，别把脏 session 留给后面的请求"
    warned = [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.auth" and record.levelno == logging.WARNING
    ]
    assert [msg for msg in warned if "last_login_time" in msg], "写失败要留下能排查的日志"


async def test_user_list_carries_last_login_time_for_both_states():
    stamp = datetime(2026, 7, 30, 9, 5, tzinfo=UTC)
    session = _FakeSession(
        [2, [_user(username="admin", last_login_time=stamp), _user(username="newbie")]]
    )

    body = await list_users(page=1, size=20, db=session)

    assert body["data"]["total"] == 2
    rows = [row.model_dump(mode="json") for row in body["data"]["list"]]
    assert [row["username"] for row in rows] == ["admin", "newbie"]
    assert datetime.fromisoformat(rows[0]["last_login_time"]) == stamp
    assert "last_login_time" in rows[1], "字段不能被裁掉，前端靠它显示「从未」"
    assert rows[1]["last_login_time"] is None


def test_response_schema_keeps_last_login_time_nullable():
    """`UserResponse` 是 /users、/users/{id}、/auth/me 共用的出参（app/schemas/user.py:41）。"""
    never = UserResponse.model_validate(_user()).model_dump(mode="json")
    assert never["last_login_time"] is None

    stamp = datetime(2026, 7, 30, 9, 5, tzinfo=UTC)
    logged_in = UserResponse.model_validate(_user(last_login_time=stamp)).model_dump(mode="json")
    assert datetime.fromisoformat(logged_in["last_login_time"]) == stamp
