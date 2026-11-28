"""Tests for /api/credentials — Keychain CRUD endpoints."""
import keyring.errors
import pytest

from src import credentials, paths

pytestmark = pytest.mark.usefixtures("isolated_keyring", "clear_credential_env")


async def test_get_credentials_returns_set_status(authed_client):
    credentials.set_credential("DISCORD_TOKEN", "x")
    response = await authed_client.get("/api/credentials")
    assert response.status_code == 200
    body = response.json()
    assert body["DISCORD_TOKEN"] is True
    assert body["NOTION_API_KEY"] is False
    assert set(body.keys()) == set(credentials.ALLOWED_KEYS)


async def test_get_credentials_requires_bearer(async_client):
    response = await async_client.get("/api/credentials")
    assert response.status_code == 401


async def test_put_credential_saves_value_and_returns_204(authed_client):
    response = await authed_client.put(
        "/api/credentials/NOTION_API_KEY",
        json={"value": "secret-key"},
    )
    assert response.status_code == 204
    assert credentials.get_credential("NOTION_API_KEY") == "secret-key"


async def test_delete_credential_removes_value_and_returns_204(authed_client):
    credentials.set_credential("CHANNEL_ID", "123")
    response = await authed_client.delete("/api/credentials/CHANNEL_ID")
    assert response.status_code == 204
    assert credentials.get_credential("CHANNEL_ID") is None


async def test_put_empty_value_returns_422(authed_client):
    response = await authed_client.put(
        "/api/credentials/DISCORD_TOKEN",
        json={"value": ""},
    )
    assert response.status_code == 422
    assert credentials.get_credential("DISCORD_TOKEN") is None


async def test_put_unknown_key_returns_400(authed_client):
    response = await authed_client.put(
        "/api/credentials/HACKER_KEY",
        json={"value": "x"},
    )
    assert response.status_code == 400


async def test_delete_unknown_key_returns_400(authed_client):
    response = await authed_client.delete("/api/credentials/HACKER_KEY")
    assert response.status_code == 400


async def test_put_credential_requires_bearer(async_client):
    response = await async_client.put(
        "/api/credentials/NOTION_API_KEY",
        json={"value": "x"},
    )
    assert response.status_code == 401


async def test_delete_credential_requires_bearer(async_client):
    response = await async_client.delete("/api/credentials/NOTION_API_KEY")
    assert response.status_code == 401


async def test_get_credential_sources_reports_where_each_value_comes_from(authed_client, monkeypatch):
    credentials.set_credential("DISCORD_TOKEN", "x")
    monkeypatch.setenv("NOTION_API_KEY", "secret-from-env")
    response = await authed_client.get("/api/credentials/sources")
    assert response.status_code == 200
    body = response.json()
    assert body["DISCORD_TOKEN"] == "keychain"
    assert body["NOTION_API_KEY"] == "env"
    assert body["CHANNEL_ID"] is None
    assert "secret-from-env" not in response.text


async def test_get_credential_sources_requires_bearer(async_client):
    response = await async_client.get("/api/credentials/sources")
    assert response.status_code == 401


# --- keyring unavailable (#616) ---


def _break_keyring(monkeypatch, error: Exception) -> None:
    class Broken:
        def get_password(self, *args):
            raise error

        set_password = delete_password = get_password

    monkeypatch.setattr(credentials, "_backend", Broken())


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (keyring.errors.NoKeyringError("no backend"), "No OS keychain backend"),
        (keyring.errors.KeyringLocked("locked"), "could not complete the request"),
    ],
)
async def test_keyring_failure_returns_503_with_env_alternative(
    authed_client, monkeypatch, method, error, reason
):
    _break_keyring(monkeypatch, error)
    kwargs = {"json": {"value": "secret-value"}} if method == "put" else {}
    response = await getattr(authed_client, method)("/api/credentials/NOTION_API_KEY", **kwargs)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert reason in detail
    assert "NOTION_API_KEY" in detail
    assert str(paths.dotenv_paths()[0]) in detail
    assert "restart" in detail
    assert "secret-value" not in response.text
