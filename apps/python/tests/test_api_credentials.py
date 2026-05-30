"""Tests for /api/credentials — Keychain CRUD endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport

from src import credentials
from web import auth
from web.app import app


@pytest.fixture(autouse=True)
def fixed_token(monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("test-token-123")
    monkeypatch.setattr(auth, "TOKEN_FILE", token_file)
    monkeypatch.setattr(auth, "_token_cache", None, raising=False)


@pytest.fixture(autouse=True)
def isolated_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}

    class _Fake:
        def get_password(self, service, name):
            return store.get((service, name))

        def set_password(self, service, name, value):
            store[(service, name)] = value

        def delete_password(self, service, name):
            store.pop((service, name), None)

    monkeypatch.setattr(credentials, "_backend", _Fake())


@pytest.fixture(autouse=True)
def clear_credential_env(monkeypatch):
    for name in credentials.ALLOWED_KEYS:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
async def test_get_credentials_returns_set_status():
    credentials.set_credential("DISCORD_TOKEN", "x")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/credentials",
            headers={"Authorization": "Bearer test-token-123"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["DISCORD_TOKEN"] is True
    assert body["NOTION_API_KEY"] is False
    assert set(body.keys()) == set(credentials.ALLOWED_KEYS)


@pytest.mark.asyncio
async def test_get_credentials_requires_bearer():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/credentials")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_put_credential_saves_value_and_returns_204():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/credentials/NOTION_API_KEY",
            headers={"Authorization": "Bearer test-token-123"},
            json={"value": "secret-key"},
        )
    assert response.status_code == 204
    assert credentials.get_credential("NOTION_API_KEY") == "secret-key"


@pytest.mark.asyncio
async def test_delete_credential_removes_value_and_returns_204():
    credentials.set_credential("CHANNEL_ID", "123")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            "/api/credentials/CHANNEL_ID",
            headers={"Authorization": "Bearer test-token-123"},
        )
    assert response.status_code == 204
    assert credentials.get_credential("CHANNEL_ID") is None


@pytest.mark.asyncio
async def test_put_empty_value_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/credentials/DISCORD_TOKEN",
            headers={"Authorization": "Bearer test-token-123"},
            json={"value": ""},
        )
    assert response.status_code == 422
    assert credentials.get_credential("DISCORD_TOKEN") is None


@pytest.mark.asyncio
async def test_put_unknown_key_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/credentials/HACKER_KEY",
            headers={"Authorization": "Bearer test-token-123"},
            json={"value": "x"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_unknown_key_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            "/api/credentials/HACKER_KEY",
            headers={"Authorization": "Bearer test-token-123"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_put_credential_requires_bearer():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/credentials/NOTION_API_KEY",
            json={"value": "x"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_credential_requires_bearer():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/credentials/NOTION_API_KEY")
    assert response.status_code == 401
