"""Tests for src/credentials.py — Keychain wrapper with .env fallback."""
import pytest

from src import credentials

pytestmark = pytest.mark.usefixtures("isolated_keyring", "clear_credential_env")


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


# --- keychain service per install (#488) ---


def test_service_name_is_ai_agent_in_the_clone_layout(monkeypatch):
    from src import paths

    monkeypatch.setattr(paths, "DATA_HOME", paths.APP_ROOT)
    assert credentials.service_name() == "ai-agent"


def test_service_name_is_separate_for_a_relocated_install(monkeypatch, tmp_path):
    """An npx install must not read the clone's keychain items: macOS would
    prompt for every item because its python binary is not on their ACL."""
    from src import paths

    monkeypatch.setattr(paths, "DATA_HOME", tmp_path)
    assert credentials.service_name() == "brief-lens"


def test_reads_and_writes_use_the_resolved_service(monkeypatch, tmp_path):
    from src import paths

    calls = []

    class _Spy:
        def get_password(self, service, name):
            calls.append(("get", service))
            return None

        def set_password(self, service, name, value):
            calls.append(("set", service))

        def delete_password(self, service, name):
            calls.append(("delete", service))

    monkeypatch.setattr(credentials, "_backend", _Spy())
    monkeypatch.setattr(paths, "DATA_HOME", tmp_path)
    credentials.get_credential("DISCORD_TOKEN")
    credentials.set_credential("DISCORD_TOKEN", "x")
    credentials.delete_credential("DISCORD_TOKEN")
    assert calls == [("get", "brief-lens"), ("set", "brief-lens"), ("delete", "brief-lens")]
