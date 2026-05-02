from unittest.mock import MagicMock, call, patch

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


# ---------------------------------------------------------------------------
# Briefing handler
# ---------------------------------------------------------------------------

class TestBriefingHandler:
    def test_success_returns_200(self):
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value="ブリーフィング本文"),
            patch("src.handler.send_to_discord"),
            patch("src.notifier.notion.Client", return_value=_notion_mock()),
        ):
            result = briefing_handler()
        assert result["statusCode"] == 200

    def test_notion_receives_model_footer(self):
        briefing_text = "ブリーフィング本文"
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=briefing_text),
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p") as mock_notion,
            patch("src.handler.get_model", return_value="claude-haiku-4-5-20251001"),
        ):
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


# ---------------------------------------------------------------------------
# XSS handler
# ---------------------------------------------------------------------------

def _xss_config_mock():
    cfg = MagicMock()
    cfg.discord_token = "tok"
    cfg.discord_channel_id = "ch"
    cfg.notion_api_key = "key"
    cfg.notion_database_id = "db"
    return cfg


class TestXssHandler:
    def test_success_returns_200(self):
        with (
            patch("src.xss_handler.get_xss_config", return_value=_xss_config_mock()),
            patch("src.xss_handler.generate_xss_report", return_value="XSSレポート本文"),
            patch("src.xss_handler.send_to_discord"),
            patch("src.notifier.notion.Client", return_value=_notion_mock()),
        ):
            result = xss_handler()
        assert result["statusCode"] == 200

    def test_report_generation_failure_returns_500(self):
        with (
            patch("src.xss_handler.get_xss_config", return_value=_xss_config_mock()),
            patch("src.xss_handler.generate_xss_report", side_effect=RuntimeError("fail")),
        ):
            result = xss_handler()
        assert result["statusCode"] == 500
        assert "generation" in result["body"]

    def test_all_notifiers_fail_returns_500(self):
        with (
            patch("src.xss_handler.get_xss_config", return_value=_xss_config_mock()),
            patch("src.xss_handler.generate_xss_report", return_value="report"),
            patch("src.xss_handler.send_to_discord", side_effect=Exception("discord fail")),
            patch("src.xss_handler.send_to_notion", side_effect=Exception("notion fail")),
        ):
            result = xss_handler()
        assert result["statusCode"] == 500
