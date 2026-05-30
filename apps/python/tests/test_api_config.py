import json

import pytest


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


async def test_get_config_returns_current(authed_client, temp_config):
    response = await authed_client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio"]["tickers"] == ["PLTR"]


async def test_get_config_requires_bearer(async_client, temp_config):
    response = await async_client.get("/api/config")
    assert response.status_code == 401


async def test_put_config_updates_file(authed_client, temp_config):
    new_config = {
        "portfolio": {"tickers": ["NVDA", "AMZN"], "themes": ["Cloud"]},
        "geopolitical": {"conflicts": []},
        "watch_sectors": [{"sector": "Cloud", "tickers": ["MSFT"], "notes": None}],
        "watch_events": [],
    }
    response = await authed_client.put("/api/config", json=new_config)
    assert response.status_code == 200
    saved = json.loads(temp_config.read_text(encoding="utf-8"))
    assert saved["portfolio"]["tickers"] == ["NVDA", "AMZN"]


async def test_put_config_rejects_empty_tickers(authed_client, temp_config):
    response = await authed_client.put(
        "/api/config",
        json={
            "portfolio": {"tickers": [], "themes": []},
            "watch_sectors": [{"sector": "AI", "tickers": ["NVDA"], "notes": None}],
        },
    )
    assert response.status_code == 422


async def test_put_config_rejects_empty_watch_sectors(authed_client, temp_config):
    response = await authed_client.put(
        "/api/config",
        json={
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "watch_sectors": [],
        },
    )
    assert response.status_code == 422


async def test_put_config_requires_bearer(async_client, temp_config):
    response = await async_client.put("/api/config", json={})
    assert response.status_code == 401


async def test_get_config_returns_500_on_corrupt_json(authed_client, temp_config):
    temp_config.write_text("not json {{{", encoding="utf-8")
    response = await authed_client.get("/api/config")
    assert response.status_code == 500
    assert "corrupt" in response.json()["detail"].lower()


async def test_get_config_returns_500_on_schema_mismatch(authed_client, temp_config):
    temp_config.write_text(
        json.dumps({"portfolio": "not-an-object", "watch_sectors": []}),
        encoding="utf-8",
    )
    response = await authed_client.get("/api/config")
    assert response.status_code == 500
    assert "schema" in response.json()["detail"].lower()


async def test_put_config_leaves_no_tmp_file_on_failure(
    authed_client_no_raise, monkeypatch, temp_config
):
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
    response = await authed_client_no_raise.put("/api/config", json=payload)
    assert response.status_code >= 500
    leftover = [p for p in temp_config.parent.iterdir() if p.suffix == ".tmp"]
    assert leftover == [], f"tmp file not cleaned up: {leftover}"
