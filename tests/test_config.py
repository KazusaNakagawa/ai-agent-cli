import json
from unittest.mock import patch

import pytest

from src.config import load_config


class TestLoadConfig:
    def test_missing_watch_sectors_raises(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            with pytest.raises(ValueError, match="watch_sectors"):
                load_config()

    def test_empty_watch_sectors_raises(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [],
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            with pytest.raises(ValueError, match="watch_sectors"):
                load_config()

    def test_sector_with_empty_tickers_raises(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [{"sector": "Tech", "tickers": []}],
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            with pytest.raises(ValueError, match="tickers"):
                load_config()

    def test_valid_config_loads_successfully(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR", "NVDA"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [{"sector": "Tech", "tickers": ["AAPL"]}],
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            config = load_config()

        assert config.portfolio.tickers == ["PLTR", "NVDA"]
        assert len(config.watch_sectors) == 1
        assert config.watch_sectors[0].sector == "Tech"

    def test_watch_events_parsed_when_present(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [{"sector": "Tech", "tickers": ["AAPL"]}],
            "watch_events": [
                {
                    "name": "SpaceX IPO",
                    "trigger": "S-1提出",
                    "affected_sectors": ["宇宙"],
                    "related_tickers": ["RKLB"],
                    "notes": "宇宙セクター再評価",
                }
            ],
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            config = load_config()

        assert len(config.watch_events) == 1
        event = config.watch_events[0]
        assert event.name == "SpaceX IPO"
        assert event.trigger == "S-1提出"
        assert event.related_tickers == ["RKLB"]

    def test_watch_events_defaults_to_empty_when_absent(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [{"sector": "Tech", "tickers": ["AAPL"]}],
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            config = load_config()

        assert config.watch_events == []
