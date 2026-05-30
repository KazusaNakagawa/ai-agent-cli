"""Tests for src/credentials.py — Keychain wrapper with .env fallback."""
import pytest

from src import credentials


@pytest.fixture(autouse=True)
def isolated_keyring(monkeypatch):
    """Replace the keyring backend with an in-memory dict."""
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
    """Strip any inherited env values for allow-listed credentials."""
    for name in credentials.ALLOWED_KEYS:
        monkeypatch.delenv(name, raising=False)


def test_set_and_get_credential():
    credentials.set_credential("DISCORD_TOKEN", "abc123")
    assert credentials.get_credential("DISCORD_TOKEN") == "abc123"


def test_get_returns_none_when_unset():
    assert credentials.get_credential("NOTION_API_KEY") is None


def test_delete_removes_credential():
    credentials.set_credential("CHANNEL_ID", "999")
    credentials.delete_credential("CHANNEL_ID")
    assert credentials.get_credential("CHANNEL_ID") is None


def test_list_returns_set_status_for_known_keys():
    credentials.set_credential("DISCORD_TOKEN", "x")
    listing = credentials.list_credentials()
    assert listing["DISCORD_TOKEN"] is True
    assert listing["NOTION_API_KEY"] is False
    assert set(listing.keys()) == set(credentials.ALLOWED_KEYS)


def test_env_fallback_when_keychain_returns_none(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "from-env")
    assert credentials.get_credential("NOTION_API_KEY") == "from-env"


def test_keychain_takes_priority_over_env(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "from-env")
    credentials.set_credential("NOTION_API_KEY", "from-keychain")
    assert credentials.get_credential("NOTION_API_KEY") == "from-keychain"


def test_get_rejects_unknown_key():
    with pytest.raises(ValueError):
        credentials.get_credential("HACKER_KEY")


def test_set_rejects_unknown_key():
    with pytest.raises(ValueError):
        credentials.set_credential("HACKER_KEY", "x")


def test_delete_rejects_unknown_key():
    with pytest.raises(ValueError):
        credentials.delete_credential("HACKER_KEY")
