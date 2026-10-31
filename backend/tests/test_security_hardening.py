"""Security hardening regression tests (auth, RBAC, share, metrics, health)."""

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.models.audit import ShareToken
from app.models.sales import Proposal
from app.schemas.user import ChangePasswordRequest, LoginRequest, ResetPasswordRequest, UserCreate


def _local_client():
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient, username: str = "admin", password: str = "admin123"):
    return await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


async def _admin_headers(client: AsyncClient) -> dict:
    response = await _login(client)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def _admin_role_id(client: AsyncClient, headers: dict) -> str:
    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200, response.text
    admin = next(item for item in response.json()["data"]["list"] if item["username"] == "admin")
    return admin["role_id"]


def _access_token(user_id: str, *, tv: int = 0) -> str:
    return create_access_token(
        {
            "sub": user_id,
            "role_code": "tester",
            "perms": [],
            "tv": tv,
        }
    )


@pytest.mark.anyio
async def test_refresh_and_file_tokens_cannot_use_user_apis():
    async with _local_client() as client:
        refresh = create_access_token(
            {"sub": str(uuid4()), "tv": 0}, token_type="refresh"
        )
        file_token = create_access_token(
            {"attachment_id": str(uuid4()), "scope": "file_content"},
            token_type="file_content",
        )
        no_tv = create_access_token(
            {"sub": str(uuid4()), "role_code": "tester", "perms": []}
        )
        for token in (refresh, file_token, no_tv):
            response = await client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 401, response.text


@pytest.mark.anyio
async def test_docs_and_openapi_are_disabled():
    from app.main import app

    assert app.docs_url is None
    assert app.openapi_url is None
    assert not any(getattr(route, "path", "") == "/openapi.json" for route in app.routes)


@pytest.mark.anyio
async def test_metrics_requires_token_or_internal_ip(monkeypatch):
    async with _local_client() as client:
        monkeypatch.setattr(settings, "APP_ENV", "production")
        monkeypatch.setattr(settings, "METRICS_TOKEN", "metrics-secret")
        denied = await client.get(
            "/api/v1/metrics", headers={"X-Real-IP": "8.8.8.8"}
        )
        assert denied.status_code == 403
        allowed = await client.get(
            "/api/v1/metrics",
            headers={"X-Real-IP": "8.8.8.8", "X-Metrics-Token": "metrics-secret"},
        )
        assert allowed.status_code == 200
        assert "pim_http_requests_total" in allowed.text


@pytest.mark.anyio
async def test_health_ready_rejects_public_ip(monkeypatch):
    async with _local_client() as client:
        monkeypatch.setattr(settings, "APP_ENV", "production")
        response = await client.get(
            "/health/ready", headers={"X-Real-IP": "8.8.8.8"}
        )
        assert response.status_code == 403


@pytest.mark.anyio
async def test_disabled_user_old_token_is_rejected(client):
    headers = await _admin_headers(client)
    admin_role = await _admin_role_id(client, headers)
    created = await client.post(
        "/api/v1/users",
        json={
            "username": "disabled-token-user",
            "password": "TempPassw0rd!",
            "role_id": admin_role,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    login = await _login(client, "disabled-token-user", "TempPassw0rd!")
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    disabled = await client.post(f"/api/v1/users/{user_id}/disable", headers=headers)
    assert disabled.status_code == 200, disabled.text

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401, response.text


@pytest.mark.anyio
async def test_non_admin_cannot_change_role_status_or_create_admin(client):
    headers = await _admin_headers(client)
    admin_role = await _admin_role_id(client, headers)
    role = await client.post(
        "/api/v1/roles",
        json={
            "role_name": "Security Tester",
            "role_code": "security_tester",
            "permission_ids": ["user:edit", "user:create", "role:edit", "role:view"],
        },
        headers=headers,
    )
    assert role.status_code == 201, role.text
    role_id = role.json()["id"]
    created = await client.post(
        "/api/v1/users",
        json={
            "username": "security-tester",
            "password": "TempPassw0rd!",
            "role_id": role_id,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    login = await _login(client, "security-tester", "TempPassw0rd!")
    assert login.status_code == 200, login.text
    tester_headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    change_status = await client.put(
        f"/api/v1/users/{user_id}",
        json={"status": "disabled"},
        headers=tester_headers,
    )
    assert change_status.status_code == 403, change_status.text

    create_admin = await client.post(
        "/api/v1/users",
        json={
            "username": "escalated-admin",
            "password": "TempPassw0rd!",
            "role_id": admin_role,
        },
        headers=tester_headers,
    )
    assert create_admin.status_code == 403, create_admin.text

    edit_admin_role = await client.put(
        f"/api/v1/roles/{admin_role}",
        json={"role_name": "x", "role_code": "admin", "permission_ids": []},
        headers=tester_headers,
    )
    assert edit_admin_role.status_code == 403, edit_admin_role.text


@pytest.mark.anyio
async def test_share_password_is_hashed_and_defaults_are_bounded(client, db):
    headers = await _admin_headers(client)
    admin = (
        await db.execute(select(Proposal.creator_id).limit(1))
    ).scalar_one_or_none()
    if admin is None:
        user_row = await client.get("/api/v1/auth/me", headers=headers)
        admin = UUID(user_row.json()["id"])
    proposal = Proposal(
        proposal_no=f"SEC{uuid4().hex[:8].upper()}",
        proposal_name="Security share",
        creator_id=admin,
    )
    db.add(proposal)
    await db.commit()

    response = await client.post(
        "/api/v1/shares",
        json={
            "share_type": "proposal",
            "target_id": str(proposal.id),
            "password": "Secret123!",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["max_access_count"] == 100
    assert data["expire_time"] is not None
    assert len(data["token"]) > 40

    stored = (
        await db.execute(select(ShareToken).where(ShareToken.token == data["token"]))
    ).scalar_one()
    assert stored.password_hash.startswith("$2")
    assert stored.password_hash != "Secret123!"
    assert stored.password != "Secret123!"


def test_share_public_payload_uses_allowlist():
    from app.api.v1.share_token import _public_share_content

    raw = {
        "proposal_no": "P-1",
        "proposal_name": "Demo",
        "customer_name": "Customer",
        "status": "confirmed",
        "total_face_value": 100,
        "items": [
            {
                "product_no": "PN-1",
                "product_name": "Chair",
                "cost_price": 10,
                "supplier_id": "supplier",
                "supplier_name": "Supplier",
                "margin": 20,
                "profit": 30,
                "scene_images": [
                    {"id": "s1", "image_url": "/x", "cost_price": 10}
                ],
                "product_snapshot": {
                    "product_no": "PN-1",
                    "cost_price": 10,
                    "supplier_name": "Supplier",
                },
            }
        ],
    }
    content = _public_share_content(raw, "proposal")
    assert content is not None
    item = content["items"][0]
    assert "cost_price" not in item
    assert "supplier_id" not in item
    assert "supplier_name" not in item
    assert "margin" not in item
    assert "profit" not in item
    assert "cost_price" not in item["product_snapshot"]
    assert "supplier_name" not in item["product_snapshot"]
    assert "cost_price" not in item["scene_images"][0]


def test_password_policy_only_applies_to_new_passwords():
    with pytest.raises(ValidationError):
        UserCreate(username="u", password="short", role_id=uuid4())
    with pytest.raises(ValidationError):
        ResetPasswordRequest(new_password="short")
    assert LoginRequest(username="u", password="short").password == "short"
    assert (
        ChangePasswordRequest(
            old_password="short", new_password="123456789012"
        ).new_password
        == "123456789012"
    )


def test_share_create_defaults_and_empty_password():
    from app.api.v1.shares import ShareCreate

    data = ShareCreate(target_id=uuid4())
    assert data.expire_hours == 168
    assert data.max_access_count == 100
    assert data.password is None
    assert ShareCreate(target_id=uuid4(), password="").password is None
    with pytest.raises(ValidationError):
        ShareCreate(target_id=uuid4(), password="short")


@pytest.mark.anyio
async def test_init_admin_does_not_overwrite_existing_account(_engine, _sessionmaker, monkeypatch):
    from app.core.security import get_password_hash, verify_password
    from app.models.user import Role, User
    from app.scripts import init_admin as init_admin_module

    monkeypatch.setattr(init_admin_module, "engine", _engine)
    monkeypatch.setattr(init_admin_module, "AsyncSessionLocal", _sessionmaker)
    monkeypatch.setenv("ADMIN_USERNAME", "sec-init-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "FirstPassw0rd!")
    monkeypatch.setenv("ADMIN_PASSWORD_RESET", "0")

    await init_admin_module.init_admin()
    async with _sessionmaker() as session:
        user = (
            await session.execute(
                select(User).where(User.username == "sec-init-admin")
            )
        ).scalar_one()
        first_hash = user.password_hash
        sales_role = (
            await session.execute(select(Role).where(Role.role_code == "sales"))
        ).scalar_one()
        user.password_hash = get_password_hash("ChangedPassw0rd!")
        user.role_id = sales_role.id
        user.status = "disabled"
        await session.commit()

    monkeypatch.setenv("ADMIN_PASSWORD", "SecondPassw0rd!")
    await init_admin_module.init_admin()
    async with _sessionmaker() as session:
        user = (
            await session.execute(
                select(User).where(User.username == "sec-init-admin")
            )
        ).scalar_one()
        assert user.password_hash != first_hash
        assert user.status == "disabled"
        assert user.role_id == sales_role.id
        changed_hash = user.password_hash
        token_version = user.token_version

    monkeypatch.setenv("ADMIN_PASSWORD_RESET", "1")
    await init_admin_module.init_admin()
    async with _sessionmaker() as session:
        user = (
            await session.execute(
                select(User).where(User.username == "sec-init-admin")
            )
        ).scalar_one()
        assert user.status == "disabled"
        assert user.role_id == sales_role.id
        assert user.token_version == token_version + 1
        assert user.password_hash != changed_hash
        assert verify_password("SecondPassw0rd!", user.password_hash)


def test_bootstrap_password_policy():
    from app.scripts.init_admin import _validate_bootstrap_password

    with pytest.raises(RuntimeError):
        _validate_bootstrap_password("admin123")
    with pytest.raises(RuntimeError):
        _validate_bootstrap_password("short")
    with pytest.raises(RuntimeError):
        _validate_bootstrap_password("__REPLACE_ME__")
    _validate_bootstrap_password("StrongPassw0rd!")
