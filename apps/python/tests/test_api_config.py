import json

import pytest
from httpx import AsyncClient, ASGITransport

from web.app import app
from web import auth


@pytest.fixture(autouse=True)
def fixed_token(monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("test-token-123")
    monkeypatch.setattr(auth, "TOKEN_FILE", token_file)
    monkeypatch.setattr(auth, "_token_cache", None, raising=False)


@pytest.fixture
def temp_config(monkeypatch, tmp_path):
    config_path = tmp_path / "briefing.json"
    initial = {
        "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
        "geopolitical": {"conflicts": []},
        "watch_sectors": [{"sector": "AI", "tickers": ["NVDA"], "notes": None}],
        "watch_events": [],
    }
    config_path.write_text(json.dumps(initial), encoding="utf-8")
    monkeypatch.setenv("BRIEFING_CONFIG_PATH", str(config_path))
    yield config_path


@pytest.mark.asyncio
async def test_get_config_returns_current(temp_config):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/config",
            headers={"Authorization": "Bearer test-token-123"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio"]["tickers"] == ["PLTR"]


@pytest.mark.asyncio
async def test_get_config_requires_bearer(temp_config):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/config")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_put_config_updates_file(temp_config):
    new_config = {
        "portfolio": {"tickers": ["NVDA", "AMZN"], "themes": ["Cloud"]},
        "geopolitical": {"conflicts": []},
        "watch_sectors": [{"sector": "Cloud", "tickers": ["MSFT"], "notes": None}],
        "watch_events": [],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/config",
            headers={"Authorization": "Bearer test-token-123"},
            json=new_config,
        )
    assert response.status_code == 200
    saved = json.loads(temp_config.read_text(encoding="utf-8"))
    assert saved["portfolio"]["tickers"] == ["NVDA", "AMZN"]


@pytest.mark.asyncio
async def test_put_config_rejects_empty_tickers(temp_config):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/config",
            headers={"Authorization": "Bearer test-token-123"},
            json={
                "portfolio": {"tickers": [], "themes": []},
                "watch_sectors": [{"sector": "AI", "tickers": ["NVDA"], "notes": None}],
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_put_config_rejects_empty_watch_sectors(temp_config):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/config",
            headers={"Authorization": "Bearer test-token-123"},
            json={
                "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
                "watch_sectors": [],
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_put_config_requires_bearer(temp_config):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put("/api/config", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_put_config_leaves_no_tmp_file_on_failure(monkeypatch, temp_config):
    """When the atomic write fails mid-flight, no .tmp file may remain."""

    def _boom(src, dst):
        raise OSError("simulated disk full")

    monkeypatch.setattr("web.routers.config.os.replace", _boom)

    payload = {
        "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
        "geopolitical": {"conflicts": []},
        "watch_sectors": [{"sector": "AI", "tickers": ["NVDA"], "notes": None}],
        "watch_events": [],
    }
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/config",
            headers={"Authorization": "Bearer test-token-123"},
            json=payload,
        )
    assert response.status_code >= 500
    leftover = [p for p in temp_config.parent.iterdir() if p.suffix == ".tmp"]
    assert leftover == [], f"tmp file not cleaned up: {leftover}"
