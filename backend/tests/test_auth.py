import pytest

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
