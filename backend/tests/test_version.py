import pytest

from app.core.config import settings

pytestmark = pytest.mark.anyio


async def _auth_headers(client):
    response = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def test_version_endpoint_returns_build_metadata(client):
    response = await client.get("/api/v1/version", headers=await _auth_headers(client))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["backend_version"] == (settings.APP_VERSION or settings.VERSION)
    assert data["build_id"]
    assert data["api_version"] == "v1"
    assert not {"DATABASE_URL", "JWT_SECRET", "MINIO_SECRET_KEY"} & data.keys()


async def test_version_endpoint_defaults_do_not_fail(client, monkeypatch):
    monkeypatch.setattr(settings, "BUILD_ID", "")
    monkeypatch.setattr(settings, "GIT_COMMIT", "")
    monkeypatch.setattr(settings, "BUILD_TIME", "")
    response = await client.get("/api/v1/version", headers=await _auth_headers(client))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["build_id"] == "dev-local"
    assert data["git_commit"] == "unknown"
    assert data["build_time"] == "unknown"


async def test_version_endpoint_requires_authentication(client):
    response = await client.get("/api/v1/version")
    assert response.status_code in (401, 403)
