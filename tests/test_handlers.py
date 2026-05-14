from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.handler import lambda_handler as briefing_handler
from src.xss_handler import lambda_handler as xss_handler


# ---------------------------------------------------------------------------
# 共通モックヘルパー
# ---------------------------------------------------------------------------

def _notion_mock():
    m = MagicMock()
    m.databases.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
    m.pages.create.return_value = {"id": "pid", "url": "https://notion.so/p"}
    return m


def _full_config_mock():
    cfg = MagicMock()
    cfg.discord_token = "tok"
    cfg.discord_channel_id = "ch"
    cfg.notion_api_key = "key"
    cfg.notion_database_id = "db"
    return cfg


def _no_api_config_mock():
    cfg = MagicMock()
    cfg.discord_token = ""
    cfg.discord_channel_id = ""
    cfg.notion_api_key = ""
    cfg.notion_database_id = ""
    return cfg


# ---------------------------------------------------------------------------
# Briefing handler
# ---------------------------------------------------------------------------

class TestBriefingHandler:
    def test_success_returns_200(self):
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value="ブリーフィング本文"),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.notifier.notion.Client", return_value=_notion_mock()),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            result = briefing_handler()
        assert result["statusCode"] == 200

    def test_notion_receives_model_footer(self):
        briefing_text = "ブリーフィング本文"
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=briefing_text),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p") as mock_notion,
            patch("src.handler.get_model", return_value="claude-haiku-4-5-20251001"),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            briefing_handler()
        expected_text = briefing_text + "\n\n---\nModel: claude-haiku-4-5-20251001"
        assert mock_notion.call_args[0][0] == expected_text

    def test_briefing_failure_propagates(self):
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", side_effect=RuntimeError("claude error")),
            patch("src.handler.send_to_discord"),
        ):
            with pytest.raises(RuntimeError, match="claude error"):
                briefing_handler()

    def test_no_credentials_writes_md_and_skips_notifiers(self, tmp_path):
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value="ブリーフィング本文"),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord") as mock_discord,
            patch("src.handler.send_to_notion") as mock_notion,
            patch("src.handler._OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = ""
            mock_cfg.discord_channel_id = ""
            mock_cfg.notion_api_key = ""
            mock_cfg.notion_database_id = ""
            result = briefing_handler()

        assert result["statusCode"] == 200
        assert result["md_fallback"] is True
        mock_discord.assert_not_called()
        mock_notion.assert_not_called()
        md_files = list(tmp_path.glob("briefing_*.md"))
        assert len(md_files) == 1

    def test_discord_only_writes_md_for_missing_notion(self, tmp_path):
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value="ブリーフィング本文"),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord") as mock_discord,
            patch("src.handler.send_to_notion") as mock_notion,
            patch("src.handler._OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = ""
            mock_cfg.notion_database_id = ""
            result = briefing_handler()

        assert result["statusCode"] == 200
        assert result["md_fallback"] is True
        mock_discord.assert_called_once()
        mock_notion.assert_not_called()
        assert len(list(tmp_path.glob("briefing_*.md"))) == 1

    def test_dry_run_skips_pipeline(self):
        with (
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.fetch_stock_moves") as mock_stocks,
            patch("src.handler.generate_briefing") as mock_gen,
        ):
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            result = briefing_handler(dry_run=True)

        assert result["statusCode"] == 200
        assert result["body"] == "dry-run"
        mock_stocks.assert_not_called()
        mock_gen.assert_not_called()

    def test_preflight_warns_on_missing_discord(self, caplog):
        import logging
        with (
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value="本文"),
            patch("src.handler.get_model", return_value="claude-sonnet-4-6"),
            patch("src.handler.send_to_notion"),
            patch("src.handler._OUTPUT_DIR", Path("/tmp")),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = ""
            mock_cfg.discord_channel_id = ""
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            with caplog.at_level(logging.WARNING, logger="src.handler"):
                briefing_handler()

        assert any("DISCORD_TOKEN" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# XSS handler
# ---------------------------------------------------------------------------

class TestXssHandler:
    def test_success_returns_200(self):
        with (
            patch("src.xss_handler.get_xss_config", return_value=_full_config_mock()),
            patch("src.xss_handler.generate_xss_report", return_value="XSSレポート本文"),
            patch("src.xss_handler.send_to_discord"),
            patch("src.notifier.notion.Client", return_value=_notion_mock()),
        ):
            result = xss_handler()
        assert result["statusCode"] == 200

    def test_report_generation_failure_returns_500(self):
        with (
            patch("src.xss_handler.get_xss_config", return_value=_full_config_mock()),
            patch("src.xss_handler.generate_xss_report", side_effect=RuntimeError("fail")),
        ):
            result = xss_handler()
        assert result["statusCode"] == 500
        assert "generation" in result["body"]

    def test_all_notifiers_fail_returns_500(self):
        with (
            patch("src.xss_handler.get_xss_config", return_value=_full_config_mock()),
            patch("src.xss_handler.generate_xss_report", return_value="report"),
            patch("src.xss_handler.send_to_discord", side_effect=Exception("discord fail")),
            patch("src.xss_handler.send_to_notion", side_effect=Exception("notion fail")),
        ):
            result = xss_handler()
        assert result["statusCode"] == 500

    def test_no_credentials_writes_md_and_skips_notifiers(self, tmp_path):
        with (
            patch("src.xss_handler.get_xss_config", return_value=_no_api_config_mock()),
            patch("src.xss_handler.generate_xss_report", return_value="XSSレポート本文"),
            patch("src.xss_handler.send_to_discord") as mock_discord,
            patch("src.xss_handler.send_to_notion") as mock_notion,
            patch("src.xss_handler._OUTPUT_DIR", tmp_path),
        ):
            result = xss_handler()

        assert result["statusCode"] == 200
        assert "md_fallback" in result["body"]
        mock_discord.assert_not_called()
        mock_notion.assert_not_called()
        md_files = list(tmp_path.glob("xss_intel_*.md"))
        assert len(md_files) == 1

    def test_dry_run_skips_pipeline(self):
        with patch("src.xss_handler.get_xss_config", return_value=_full_config_mock()):
            with patch("src.xss_handler.generate_xss_report") as mock_gen:
                result = xss_handler(dry_run=True)

        assert result["statusCode"] == 200
        assert result["body"] == "dry-run"
        mock_gen.assert_not_called()
