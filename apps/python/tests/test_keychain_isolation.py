import keyring
from keyring.backends import null

from src import credentials


def test_pytest_never_uses_the_real_keychain():
    # A real backend would pop a macOS Keychain dialog and block the run (#548).
    assert isinstance(keyring.get_keyring(), null.Keyring)


def test_unisolated_lookup_reads_nothing_from_keychain(monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    assert credentials.get_credential("NOTION_API_KEY") is None
