import os
from pathlib import Path

# テスト実行時は tests/config/briefing.json を使用し、本番設定を読まない。
# src.config の import 前に環境変数を立てる必要があるので、conftest 最上位で実行する。
os.environ.setdefault("BRIEFING_CONFIG_PATH", str(Path(__file__).parent / "config" / "briefing.json"))

import pytest
from httpx import ASGITransport, AsyncClient

from src import credentials, state as state_mod
from web import auth
from web.app import app

TEST_TOKEN = "test-token-123"


@pytest.fixture
def fixed_token(monkeypatch, tmp_path):
    """Pin auth.TOKEN_FILE to a tmp path with a known token."""
    token_file = tmp_path / "token"
    token_file.write_text(TEST_TOKEN)
    monkeypatch.setattr(auth, "TOKEN_FILE", token_file)
    monkeypatch.setattr(auth, "_token_cache", None, raising=False)


@pytest.fixture
def isolated_keyring(monkeypatch):
    """Swap the keyring backend for an in-memory dict so tests never touch the real Keychain."""
    store: dict[tuple[str, str], str] = {}

    class _Fake:
        def get_password(self, service, name):
            return store.get((service, name))

        def set_password(self, service, name, value):
            store[(service, name)] = value

        def delete_password(self, service, name):
            store.pop((service, name), None)

    monkeypatch.setattr(credentials, "_backend", _Fake())


@pytest.fixture
def clear_credential_env(monkeypatch):
    """Strip any inherited env values for allow-listed credentials so .env fallback can't leak in."""
    for name in credentials.ALLOWED_KEYS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def isolated_state(monkeypatch, tmp_path):
    """Pin ``state.STATE_FILE`` to a tmp path so tests are independent of the
    host's ``~/.ai-agent/state.json``."""
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "state.json")


@pytest.fixture
async def async_client(fixed_token):
    """Bare httpx AsyncClient with no Authorization header. Use for 401 / unauth tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def authed_client(fixed_token):
    """httpx AsyncClient pre-loaded with the test Bearer token."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client


@pytest.fixture
async def authed_client_no_raise(fixed_token):
    """Like authed_client but lets the app's unhandled exceptions bubble up as 5xx responses
    instead of being re-raised through the ASGI transport. Use for tests that simulate
    crash-paths inside route handlers."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
