import pytest

from web import auth


async def test_health_does_not_require_auth(async_client):
    response = await async_client.get("/api/health")
    assert response.status_code == 200


async def test_protected_route_rejects_without_bearer(async_client):
    response = await async_client.get("/api/config")
    assert response.status_code in (401, 404)


def test_token_file_has_mode_600(tmp_path, monkeypatch):
    # Fresh path so the conftest fixed_token fixture doesn't pre-create it.
    token_file = tmp_path / "fresh-token"
    monkeypatch.setattr(auth, "TOKEN_FILE", token_file)
    monkeypatch.setattr(auth, "_token_cache", None, raising=False)

    auth._ensure_token()

    assert token_file.exists()
    mode = token_file.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_require_bearer_rejects_missing_header(fixed_token):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        auth.require_bearer(authorization="")
    assert exc_info.value.status_code == 401


def test_require_bearer_rejects_wrong_token(fixed_token):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        auth.require_bearer(authorization="Bearer wrong-token")
    assert exc_info.value.status_code == 401


def test_require_bearer_accepts_correct_token(fixed_token):
    auth.require_bearer(authorization="Bearer test-token-123")
