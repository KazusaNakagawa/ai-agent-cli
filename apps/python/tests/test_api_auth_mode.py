"""Tests for /api/auth/mode — CLI/API mode switching."""
import json

import pytest

from src import state as state_mod


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "state.json")


async def test_get_auth_mode_returns_cli_by_default(authed_client):
    response = await authed_client.get("/api/auth/mode")
    assert response.status_code == 200
    assert response.json() == {"auth_mode": "cli"}


async def test_get_auth_mode_requires_bearer(async_client):
    response = await async_client.get("/api/auth/mode")
    assert response.status_code == 401


async def test_put_auth_mode_to_api(authed_client):
    response = await authed_client.put("/api/auth/mode", json={"auth_mode": "api"})
    assert response.status_code == 200
    assert response.json() == {"auth_mode": "api"}
    assert state_mod.read_state().auth_mode == "api"


async def test_put_auth_mode_back_to_cli(authed_client):
    state_mod.write_state(state_mod.State(auth_mode="api"))
    response = await authed_client.put("/api/auth/mode", json={"auth_mode": "cli"})
    assert response.status_code == 200
    assert state_mod.read_state().auth_mode == "cli"


async def test_put_invalid_mode_returns_422(authed_client):
    response = await authed_client.put("/api/auth/mode", json={"auth_mode": "oauth"})
    assert response.status_code == 422


async def test_put_auth_mode_requires_bearer(async_client):
    response = await async_client.put("/api/auth/mode", json={"auth_mode": "api"})
    assert response.status_code == 401


async def test_put_preserves_other_state_fields(authed_client):
    state_mod.write_state(
        state_mod.State(onboarded=True, auth_mode="cli", migrated_from_env=True)
    )
    await authed_client.put("/api/auth/mode", json={"auth_mode": "api"})
    after = state_mod.read_state()
    assert after.auth_mode == "api"
    assert after.onboarded is True
    assert after.migrated_from_env is True
