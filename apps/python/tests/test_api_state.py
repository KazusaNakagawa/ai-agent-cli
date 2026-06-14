"""Tests for /api/state — full state read + partial update."""
import pytest

from src import state as state_mod


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "state.json")


async def test_get_state_returns_defaults_when_file_missing(authed_client):
    response = await authed_client.get("/api/state")
    assert response.status_code == 200
    assert response.json() == {
        "onboarded": False,
        "auth_mode": "cli",
        "migrated_from_env": False,
        "version": 1,
    }


async def test_get_state_requires_bearer(async_client):
    response = await async_client.get("/api/state")
    assert response.status_code == 401


async def test_put_state_flips_onboarded_and_preserves_other_fields(authed_client):
    state_mod.write_state(state_mod.State(auth_mode="api"))
    response = await authed_client.put("/api/state", json={"onboarded": True})
    assert response.status_code == 200
    assert response.json() == {
        "onboarded": True,
        "auth_mode": "api",
        "migrated_from_env": False,
        "version": 1,
    }
    persisted = state_mod.read_state()
    assert persisted.onboarded is True
    assert persisted.auth_mode == "api"


async def test_put_state_partial_update_leaves_unspecified_fields_alone(authed_client):
    state_mod.write_state(
        state_mod.State(onboarded=True, auth_mode="api", migrated_from_env=True)
    )
    response = await authed_client.put("/api/state", json={"auth_mode": "cli"})
    assert response.status_code == 200
    body = response.json()
    assert body["onboarded"] is True
    assert body["auth_mode"] == "cli"
    assert body["migrated_from_env"] is True


async def test_put_invalid_auth_mode_returns_422(authed_client):
    response = await authed_client.put("/api/state", json={"auth_mode": "oauth"})
    assert response.status_code == 422


async def test_put_state_ignores_unknown_fields(authed_client):
    # Pydantic defaults: unknown fields are silently dropped (not extra=forbid).
    # The endpoint should still succeed and not crash.
    response = await authed_client.put(
        "/api/state", json={"onboarded": True, "version": 99}
    )
    assert response.status_code == 200
    assert response.json()["version"] == 1  # version unchanged
    assert response.json()["onboarded"] is True
