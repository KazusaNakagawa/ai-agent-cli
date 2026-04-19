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
