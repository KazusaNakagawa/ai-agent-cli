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


class TestSeedConfig:
    @pytest.fixture
    def template(self, monkeypatch, tmp_path):
        path = tmp_path / "briefing.json.example"
        path.write_text('{"portfolio": {"tickers": ["EXAMPLE"]}}\n', encoding="utf-8")
        monkeypatch.setattr("web.routers.config._template_path", lambda: path)
        return path

    async def test_creates_briefing_json_from_the_template_when_missing(
        self, authed_client, monkeypatch, tmp_path, template
    ):
        target = tmp_path / "config" / "briefing.json"
        monkeypatch.setenv("BRIEFING_CONFIG_PATH", str(target))

        response = await authed_client.post("/api/config/seed")

        assert response.status_code == 200
        assert response.json() == {"created": True}
        assert target.read_text(encoding="utf-8") == template.read_text(encoding="utf-8")

    async def test_leaves_an_existing_briefing_json_alone(
        self, authed_client, temp_config, template
    ):
        before = temp_config.read_text(encoding="utf-8")

        response = await authed_client.post("/api/config/seed")

        assert response.status_code == 200
        assert response.json() == {"created": False}
        assert temp_config.read_text(encoding="utf-8") == before

    async def test_reports_a_missing_template(self, authed_client, monkeypatch, tmp_path):
        target = tmp_path / "briefing.json"
        monkeypatch.setenv("BRIEFING_CONFIG_PATH", str(target))
        monkeypatch.setattr("web.routers.config._template_path", lambda: tmp_path / "nope.example")

        response = await authed_client.post("/api/config/seed")

        assert response.status_code == 500
        assert "template" in response.json()["detail"]
        assert not target.exists()

    async def test_requires_bearer(self, async_client, temp_config):
        response = await async_client.post("/api/config/seed")
        assert response.status_code == 401
