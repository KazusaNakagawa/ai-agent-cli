import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import get_journal_chat_trusted_write_dirs, get_obsidian_config, load_config


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

    def test_obsidian_config_parsed_when_present(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [{"sector": "Tech", "tickers": ["AAPL"]}],
            "obsidian": {"vault_path": "/tmp/vault"},
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            config = load_config()

        assert config.obsidian is not None
        assert config.obsidian.vault_path == "/tmp/vault"
        assert config.obsidian.journal_subdir == "journal"
        assert config.obsidian.exclude_dirs == [".obsidian", ".trash", "templates"]

    def test_obsidian_config_none_when_absent(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [{"sector": "Tech", "tickers": ["AAPL"]}],
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            assert load_config().obsidian is None
            assert get_obsidian_config() is None

    def test_get_obsidian_config_returns_none_when_file_missing(self, tmp_path):
        with patch("src.config.CONFIG_PATH", tmp_path / "missing.json"):
            assert get_obsidian_config() is None

    def test_journal_chat_trusted_write_dirs_defaults_to_empty(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [{"sector": "Tech", "tickers": ["AAPL"]}],
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            assert load_config().journal_chat.trusted_write_dirs == []
            assert get_journal_chat_trusted_write_dirs() == []

    def test_journal_chat_trusted_write_dirs_parsed_when_present(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [{"sector": "Tech", "tickers": ["AAPL"]}],
            "journal_chat": {"trusted_write_dirs": ["/tmp/zenn-docs"]},
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            assert load_config().journal_chat.trusted_write_dirs == ["/tmp/zenn-docs"]
            assert get_journal_chat_trusted_write_dirs() == ["/tmp/zenn-docs"]

    def test_get_journal_chat_trusted_write_dirs_expands_home(self, tmp_path):
        data = {
            "portfolio": {"tickers": ["PLTR"], "themes": ["AI"]},
            "geopolitical": {"conflicts": []},
            "watch_sectors": [{"sector": "Tech", "tickers": ["AAPL"]}],
            "journal_chat": {"trusted_write_dirs": ["~/work/zenn-docs"]},
        }
        config_file = tmp_path / "briefing.json"
        config_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("src.config.CONFIG_PATH", config_file):
            dirs = get_journal_chat_trusted_write_dirs()

        assert dirs == [str(Path("~/work/zenn-docs").expanduser())]
        assert "~" not in dirs[0]

    def test_get_journal_chat_trusted_write_dirs_returns_empty_when_file_missing(self, tmp_path):
        with patch("src.config.CONFIG_PATH", tmp_path / "missing.json"):
            assert get_journal_chat_trusted_write_dirs() == []

    def test_importing_src_config_does_not_eagerly_read_file(self, tmp_path):
        """Regression: importing src.config must not read briefing.json at
        module-load time. The FastAPI web server (web.app → web.routers.config
        → web.schemas → src.config) needs to boot before briefing.json exists
        — its whole purpose is to let the operator create that file via
        /api/config. Spawning a fresh interpreter so this test doesn't depend
        on whatever state src.config is already in for the current process."""
        missing = tmp_path / "definitely-missing.json"
        assert not missing.exists()

        env = {**os.environ, "BRIEFING_CONFIG_PATH": str(missing)}
        apps_python = Path(__file__).parent.parent  # apps/python

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import src.config; from web.app import app; print('imported-ok')",
            ],
            env=env,
            cwd=apps_python,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            f"importing failed unexpectedly\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "imported-ok" in result.stdout
