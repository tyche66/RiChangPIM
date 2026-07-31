"""单元测试：操作日志真实用户名（不依赖 DB）。

断言的位置很关键：``username`` **不是**装饰器传给 ``_write_operation_log`` 的关键字，
而是 ``_write_operation_log`` 内部查出来、写在 ``OperationLog`` 行上的字段。所以这里
用假 session 顶掉 ``AsyncSessionLocal``，直接检查 ``session.add()`` 收到的那一行。

反面教材（本文件上一版）：对着 ``_write_operation_log`` 的 ``username`` 关键字断言
``is None``。那个关键字根本不存在，``kwargs.get("username")`` 恒为 ``None``，于是
「匿名 / 过期 / 已删号 → 留空」三条断言永远成立——就算落库时写死「未知用户」也照样绿，
等于没测；而「正常用户 → 有名字」那条则必然红。

覆盖三种查不到人的情况：匿名请求、令牌过期、用户已被物理删除。三种都必须留空
（``None``）交给前端退化显示（``frontend/src/views/Logs.vue`` 的 ``shortId()``），
不许落「未知用户」这类占位值。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.middleware.audit import audit_action


class _State:
    def __init__(self, **kw: Any):
        self.__dict__.update(kw)


class _Request:
    """简化 Request（沿用 tests/test_audit.py 的写法）：headers / client / state / body()。"""

    def __init__(self, *, state_user_id: str | None = None, authorization: str | None = None):
        self.headers: dict[str, str] = {}
        if authorization:
            self.headers["authorization"] = authorization
        self.client = MagicMock()
        self.client.host = "10.0.0.1"
        self.state = _State(user_id=state_user_id)

    async def body(self) -> bytes:
        return b""


class _FakeResult:
    def __init__(self, value: Any):
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeSession:
    """够 ``_write_operation_log`` / ``_resolve_username`` 用的最小 async session。"""

    def __init__(self, *, username: str | None = None, execute_error: bool = False):
        self._username = username
        self._execute_error = execute_error
        self.added: list[Any] = []
        self.committed = False
        self.executed = 0

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    async def execute(self, _stmt: Any) -> _FakeResult:
        self.executed += 1
        if self._execute_error:
            raise RuntimeError("user table unavailable")
        return _FakeResult(self._username)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def close(self) -> None:
        return None


async def _audited_row(session: _FakeSession, request: _Request) -> Any:
    """跑完整链路（装饰器 → 真的 ``_write_operation_log``），返回落库的那一行。

    ``_write_operation_log`` 会吞掉所有异常（审计不许影响主流程），所以这里额外断言
    「真的 add 了一行且 commit 过」：万一 patch 打偏或假 session 不够用，异常被吞掉后
    测试会在这两条上变红，而不是静默通过。
    """

    @audit_action("test_action", module="test")
    async def handler(request: Any) -> dict[str, int]:
        return {"code": 200}

    with patch("app.core.database.AsyncSessionLocal", return_value=session):
        await handler(request=request)

    assert len(session.added) == 1, "审计行没落库：_write_operation_log 里抛的异常被吞了"
    assert session.committed, "审计行必须 commit，否则等于没写"
    return session.added[0]


@pytest.mark.anyio
async def test_username_none_for_anonymous_request():
    """匿名请求：没有 user_id，username 留空，而且根本不该去查 user 表。"""
    session = _FakeSession(username="never-used")
    row = await _audited_row(session, _Request())

    assert row.user_id is None
    assert row.username is None
    assert session.executed == 0


@pytest.mark.anyio
async def test_username_none_for_expired_token():
    """令牌过期：decode 抛异常 → 取不到 sub → 退化成匿名，username 留空。"""
    session = _FakeSession(username="never-used")
    with patch("app.core.security.decode_access_token", side_effect=ValueError("expired")):
        row = await _audited_row(session, _Request(authorization="Bearer expired-token"))

    assert row.user_id is None
    assert row.username is None
    assert session.executed == 0


@pytest.mark.anyio
async def test_username_none_for_deleted_user():
    """用户已被物理删除：有 user_id 但查不到名字，留空，不编造。"""
    session = _FakeSession(username=None)
    row = await _audited_row(session, _Request(state_user_id="deleted-uuid"))

    assert row.user_id == "deleted-uuid"
    assert row.username is None
    assert session.executed == 1


@pytest.mark.anyio
async def test_username_snapshot_for_valid_user():
    """正常用户：真实用户名定格在行上。

    这条是本文件唯一会因为「落库时漏写 username」而变红的断言——上一版把它写在了
    不存在的关键字上，所以真漏写也照样绿。
    """
    session = _FakeSession(username="zhangsan")
    row = await _audited_row(session, _Request(state_user_id="user-1"))

    assert row.user_id == "user-1"
    assert row.username == "zhangsan"


@pytest.mark.anyio
async def test_lookup_failure_still_writes_the_row():
    """查名字这一步炸了不能把整条审计丢掉：username 留空，行照样落库。"""
    session = _FakeSession(execute_error=True)
    row = await _audited_row(session, _Request(state_user_id="user-1"))

    assert row.user_id == "user-1"
    assert row.username is None


@pytest.mark.anyio
async def test_no_placeholder_username_for_unknown_operators():
    """三种查不到人的情况一律留空，不许出现「未知用户」这类占位值。"""
    anonymous = await _audited_row(_FakeSession(username="x"), _Request())
    deleted = await _audited_row(_FakeSession(username=None), _Request(state_user_id="gone"))
    with patch("app.core.security.decode_access_token", side_effect=ValueError("expired")):
        expired = await _audited_row(
            _FakeSession(username="x"), _Request(authorization="Bearer e")
        )

    for label, row in (("匿名请求", anonymous), ("已删除用户", deleted), ("令牌过期", expired)):
        assert row.username is None, f"{label}：username 必须留空，实际落库 {row.username!r}"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
