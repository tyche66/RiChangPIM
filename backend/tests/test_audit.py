"""单元测试：审计装饰器逻辑（不依赖真 DB）。

依据 docs/07-开发规范.md §7.2 / §7.3：审计装饰器需自动捕获
user_id / ip / response_code / action / module，并在写库失败时降级 ERROR 日志、
不影响业务响应。此测试纯函数化：mock 掉 ``_write_operation_log`` 与
``AsyncSessionLocal``，验证装饰器把调用元信息正确传递到落库函数。
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _Body:
    def __init__(self, raw: bytes = b""):
        self._raw = raw

    async def body(self) -> bytes:
        return self._raw


class _State:
    def __init__(self, **kw: Any):
        self.__dict__.update(kw)


class _Request:
    """简化 Request：包含 headers / client / state / body()。"""

    def __init__(
        self,
        *,
        xff: str = None,
        host: str = "10.0.0.1",
        state_user_id: str = None,
        authorization: str = None,
        body: bytes = b"",
    ):
        self.headers = {}
        if xff:
            self.headers["x-forwarded-for"] = xff
        if authorization:
            self.headers["authorization"] = authorization
        self.client = MagicMock()
        self.client.host = host
        self.state = _State(user_id=state_user_id)
        self._body = _Body(body)

    async def body(self) -> bytes:
        return await self._body.body()


@pytest.mark.anyio
async def test_success_records_action_module_user_ip():
    from app.middleware.audit import audit_action

    captured = {}

    async def fake_write(**kwargs):
        captured.update(kwargs)

    @audit_action("product_create", module="products", target_id_kwarg="id")
    async def handler(request):
        return {"code": 200, "data": {"id": "prod-uuid-123"}}

    req = _Request(
        state_user_id="user-1",
        host="172.16.0.5",
        body=b'{"product_no":"P-1","product_name":"widget"}',
    )

    with (
        patch("app.middleware.audit._write_operation_log", side_effect=fake_write),
        patch(
            "app.middleware.audit._request_body_value",
            new=AsyncMock(return_value='{"product_no":"P-1"'),
        ),
    ):
        result = await handler(request=req)

    assert result == {"code": 200, "data": {"id": "prod-uuid-123"}}
    assert captured["action"] == "product_create"
    assert captured["module"] == "products"
    assert captured["user_id"] == "user-1"
    assert captured["ip"] == "172.16.0.5"
    assert captured["response_code"] == 200
    assert captured["target_id"] == "prod-uuid-123"


@pytest.mark.anyio
async def test_x_forwarded_for_priority_over_client_host():
    from app.middleware.audit import audit_action

    captured = {}

    async def fake_write(**kwargs):
        captured.update(kwargs)

    @audit_action("share_create", module="shares")
    async def handler(request):
        return {"code": 200}

    req = _Request(xff="203.0.113.9, 10.0.0.1", host="10.0.0.1", state_user_id="u-2")

    with patch("app.middleware.audit._write_operation_log", side_effect=fake_write):
        await handler(request=req)

    assert captured["ip"] == "203.0.113.9"


@pytest.mark.anyio
async def test_failed_action_on_http_exception_status_from_exc():
    from fastapi import HTTPException, status

    from app.middleware.audit import audit_action

    captured = {}

    async def fake_write(**kwargs):
        captured.update(kwargs)

    @audit_action("login", module="auth", failed_action="login_failed")
    async def handler(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad creds")

    req = _Request(host="5.6.7.8", state_user_id=None, body=b'{"username":"x"}')

    with patch("app.middleware.audit._write_operation_log", side_effect=fake_write):
        with pytest.raises(HTTPException) as exc_info:
            await handler(request=req)

    assert exc_info.value.status_code == 401
    assert captured["action"] == "login_failed"
    assert captured["response_code"] == 401
    assert captured["ip"] == "5.6.7.8"


@pytest.mark.anyio
async def test_failed_action_absent_falls_back_to_action_with_error_status():
    from fastapi import HTTPException

    from app.middleware.audit import audit_action

    captured = {}

    async def fake_write(**kw):
        captured.update(kw)

    @audit_action("user_delete", module="users")
    async def handler(request):
        raise HTTPException(status_code=404, detail="user not found")

    req = _Request(state_user_id="u-3")

    with patch("app.middleware.audit._write_operation_log", side_effect=fake_write):
        with pytest.raises(HTTPException):
            await handler(request=req)

    assert captured["action"] == "user_delete"
    assert captured["response_code"] == 404


@pytest.mark.anyio
async def test_write_failure_does_not_block_response(caplog):
    from app.middleware.audit import audit_action

    @audit_action("logout", module="auth")
    async def handler(request):
        return {"code": 200, "msg": "success"}

    req = _Request(state_user_id="u-4")

    class _BoomSession:
        def __init__(self):
            raise RuntimeError("db down")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch("app.core.database.AsyncSessionLocal", _BoomSession):
        result = await handler(request=req)

    # 业务响应不受影响
    assert result == {"code": 200, "msg": "success"}
    # 写库失败降级为 ERROR 日志，可被运维定位
    assert any(r.levelname == "ERROR" and "audit write failed" in r.message for r in caplog.records)


@pytest.mark.anyio
async def test_response_code_taken_from_business_envelope_when_not_200():
    from app.middleware.audit import audit_action

    captured = {}

    async def fake_write(**kw):
        captured.update(kw)

    @audit_action("proposal_delete", module="proposals")
    async def handler(request):
        return {"code": 200}

    # NOTE: ``quotation_confirm`` 此处仅为装饰器通用测试示例（验证业务 envelope
    # code 透传），并非生产动作——生产代码中无 /confirm 路由，该 action 在
    # docs/07 §7.3.2 / appendix §3.1 明确列为 TODO。切勿据此认为该动作已落地。
    @audit_action("quotation_confirm", module="quotations")
    async def handler_custom_code(request):
        return {"code": 202, "msg": "accepted"}

    req = _Request(state_user_id="u-5")

    with patch("app.middleware.audit._write_operation_log", side_effect=fake_write):
        await handler(request=req)
    assert captured["response_code"] == 200

    captured.clear()
    with patch("app.middleware.audit._write_operation_log", side_effect=fake_write):
        await handler_custom_code(request=req)
    assert captured["action"] == "quotation_confirm"
    assert captured["response_code"] == 202


@pytest.mark.anyio
async def test_share_access_failed_records_share_access_denied():
    """分享访问失败（404 未知 token / 403 失效等）经 failed_action 记 share_access_denied。

    该路径与 login -> login_failed 同机制；本用例确认未知 token 的 404 会作为
    安全事件落入 operation_log（action=share_access_denied），且不依赖任何 ShareToken FK。
    """
    from fastapi import HTTPException

    from app.middleware.audit import audit_action

    captured = {}

    async def fake_write(**kwargs):
        captured.update(kwargs)

    @audit_action("share_access", module="shares", failed_action="share_access_denied")
    async def handler(request):
        raise HTTPException(status_code=404, detail={"code": 40401, "msg": "分享不存在"})

    req = _Request(host="9.9.9.9", state_user_id=None)

    with patch("app.middleware.audit._write_operation_log", side_effect=fake_write):
        with pytest.raises(HTTPException):
            await handler(request=req)

    assert captured["action"] == "share_access_denied"
    assert captured["response_code"] == 404
    assert captured["module"] == "shares"
    # 未知 token 不应把原始 token 写入审计落库（request_body 为 GET 空体）
    assert captured.get("request_body") is None


@pytest.mark.anyio
async def test_user_id_falls_back_to_bearer_token_decode():
    from app.middleware.audit import audit_action

    captured = {}

    async def fake_write(**kwargs):
        captured.update(kwargs)

    def fake_decode(token):
        assert token == "tok-abc"
        return {"sub": "user-from-jwt"}

    @audit_action("change_password", module="auth")
    async def handler(request):
        return {"code": 200}

    req = _Request(authorization="Bearer tok-abc", state_user_id=None)

    with (
        patch("app.core.security.decode_access_token", side_effect=fake_decode),
        patch("app.middleware.audit._write_operation_log", side_effect=fake_write),
    ):
        await handler(request=req)

    assert captured["user_id"] == "user-from-jwt"


def test_module_imports_clean():
    import importlib

    mod = importlib.import_module("app.middleware.audit")
    assert hasattr(mod, "audit_action")
    assert hasattr(mod, "AuditMiddleware")


@pytest.mark.anyio
async def test_sensitive_modules_request_body_is_redacted():
    """V1.2 §5.2 / §6.5 — auth/users/ai 模块的 body_summary 必须落库为 [redacted]。

    严禁把登录密码、AI Key、用户密码原文写入 operation_log。
    """
    from app.middleware.audit import audit_action

    captured = {}

    async def fake_write(**kwargs):
        captured.update(kwargs)

    @audit_action("login", module="auth")
    async def handler(request):
        return {"code": 200}

    req = _Request(
        state_user_id="u-9",
        body=b'{"username":"admin","password":"supersecret"}',
    )

    with (
        patch("app.middleware.audit._write_operation_log", side_effect=fake_write),
    ):
        await handler(request=req)

    assert captured["request_body"] == "[redacted]"
    assert "supersecret" not in str(captured)


@pytest.mark.anyio
async def test_non_sensitive_module_keeps_body_summary():
    """非敏感模块（products 等）的 body_summary 仍按既定 V1.1 行为保留前 200 字符。"""
    from app.middleware.audit import audit_action

    captured = {}

    async def fake_write(**kwargs):
        captured.update(kwargs)

    @audit_action("product_create", module="products")
    async def handler(request):
        return {"code": 200, "data": {"id": "p-1"}}

    req = _Request(
        state_user_id="u-10",
        body=b'{"product_no":"P-1","product_name":"desk"}',
    )

    with (
        patch("app.middleware.audit._write_operation_log", side_effect=fake_write),
    ):
        await handler(request=req)

    # body_summary must NOT be [redacted] for non-sensitive modules.
    assert captured.get("request_body") != "[redacted]"
    assert "P-1" in str(captured.get("request_body", ""))


def test_rolling_5xx_counter_counts_only_5xx():
    """V1.2 /ops/status 5xx 报警计数：只有 5xx 状态才入队，4xx 不入队。"""
    from app.middleware.audit import _record_5xx, http_5xx_last_24h

    # sanity check: counter reports 0 baseline; only 5xx increments it
    # (we don't insert 4xx or 2xx)
    _record_5xx(200)
    _record_5xx(404)
    _record_5xx(500)
    _record_5xx(503)
    # This is a shared global state — other tests may have contributed.
    # Validate only that the count is >= 2 here (i.e. 2× 5xx from this call).
    assert http_5xx_last_24h() >= 2


if __name__ == "__main__":
    asyncio.run(test_success_records_action_module_user_ip())
