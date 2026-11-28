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


def _break_keyring(monkeypatch, **behaviour) -> None:
    """Replace the backend; each kwarg is a value to return or an exception to raise."""

    def method(outcome):
        def call(*args):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return staticmethod(call)

    broken = type("Broken", (), {name: method(outcome) for name, outcome in behaviour.items()})
    monkeypatch.setattr(credentials, "_backend", broken())


async def _call(client, method):
    kwargs = {"json": {"value": "secret-value"}} if method == "put" else {}
    return await getattr(client, method)("/api/credentials/NOTION_API_KEY", **kwargs)


@pytest.mark.parametrize(("method", "verb"), [("put", "add"), ("delete", "remove")])
async def test_no_keyring_backend_returns_503_with_env_alternative(
    authed_client, monkeypatch, method, verb
):
    error = keyring.errors.NoKeyringError("no backend")
    _break_keyring(monkeypatch, get_password=error, set_password=error, delete_password=error)
    response = await _call(authed_client, method)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "No OS keychain backend" in detail
    assert f"{verb} " in detail and "NOTION_API_KEY" in detail
    assert str(paths.dotenv_paths()[0]) in detail
    assert "restart" in detail
    assert "secret-value" not in response.text


async def test_locked_keychain_on_put_does_not_suggest_env(authed_client, monkeypatch):
    # An older keychain value would still win over .env.
    _break_keyring(monkeypatch, set_password=keyring.errors.KeyringLocked("locked"))
    response = await _call(authed_client, "put")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "could not save NOTION_API_KEY" in detail
    assert ".env" not in detail
    assert "secret-value" not in response.text


@pytest.mark.parametrize(
    ("delete_error", "lookup"),
    [
        (keyring.errors.KeyringLocked("locked"), "still-stored"),
        (keyring.errors.PasswordDeleteError("denied"), "still-stored"),
        (keyring.errors.PasswordDeleteError("denied"), keyring.errors.KeyringLocked("locked")),
    ],
)
async def test_failed_delete_says_the_entry_was_not_removed(
    authed_client, monkeypatch, delete_error, lookup
):
    _break_keyring(monkeypatch, delete_password=delete_error, get_password=lookup)
    response = await _call(authed_client, "delete")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "was not removed" in detail
    assert ".env" not in detail
    assert "still-stored" not in response.text


async def test_delete_of_an_absent_entry_returns_204(authed_client, monkeypatch):
    _break_keyring(
        monkeypatch,
        delete_password=keyring.errors.PasswordDeleteError("No such password!"),
        get_password=None,
    )
    response = await _call(authed_client, "delete")
    assert response.status_code == 204
