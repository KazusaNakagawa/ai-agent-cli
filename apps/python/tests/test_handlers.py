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


# A generate_briefing() mock return value must pass looks_like_briefing()
# (heading + minimum length, #409) or the handler raises before delivery.
_VALID_BRIEFING = "### ブリーフィング本文\n\n" + "本文です。" * 40


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

@pytest.fixture(autouse=False)
def disable_skip_guard():
    """Disable BRIEFING_SKIP_IF_EXISTS for tests that don't exercise the guard.

    Apply to any test that calls briefing_handler() without mocking
    BRIEFING_OUTPUT_DIR, to prevent false-skips when today's MD already exists
    on the developer's machine.
    """
    with patch("src.handler.BRIEFING_SKIP_IF_EXISTS", False):
        yield


class TestBriefingHandler:
    def test_success_returns_200(self, tmp_path):
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.notifier.notion.Client", return_value=_notion_mock()),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            result = briefing_handler()
        assert result["statusCode"] == 200

    def test_md_written_even_when_notifiers_succeed(self, tmp_path):
        """Verifies: when Discord/Notion both succeed, a local MD file is
        still written under BRIEFING_OUTPUT_DIR.
        Why: the new always-write requirement (issue #38). Operators need a
        local copy regardless of remote-notifier success.
        """
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p"),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            result = briefing_handler()

        assert result["md_written"] is True
        md_files = list(tmp_path.glob("briefing_*.md"))
        assert len(md_files) == 1
        assert md_files[0].read_text(encoding="utf-8") == _VALID_BRIEFING

    def test_md_written_even_when_discord_raises(self, tmp_path):
        """Verifies: when send_to_discord raises, the local MD file is still
        written before the exception propagates.
        Why: issue #38 specifies Discord/Notion/local MD as three independent
        outputs. A Discord outage must not prevent the local copy from being
        saved — that copy is the operator's diagnostic fallback.
        """
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord", side_effect=RuntimeError("discord down")),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p"),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            with pytest.raises(RuntimeError, match="discord down"):
                briefing_handler()

        md_files = list(tmp_path.glob("briefing_*.md"))
        assert len(md_files) == 1
        assert md_files[0].read_text(encoding="utf-8") == _VALID_BRIEFING

    @pytest.mark.usefixtures("disable_skip_guard")
    def test_md_failure_does_not_block_pipeline(self, tmp_path):
        """Verifies: if save_briefing_md raises, the handler still returns
        200 with md_written=False.
        Why: a disk-write failure must not lose the Discord/Notion deliveries
        that already succeeded.
        """
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord") as mock_discord,
            patch("src.handler.send_to_notion", return_value="https://notion.so/p") as mock_notion,
            patch("src.handler.save_briefing_md", side_effect=OSError("disk full")),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            result = briefing_handler()

        assert result["statusCode"] == 200
        assert result["md_written"] is False
        mock_discord.assert_called_once()
        mock_notion.assert_called_once()

    @pytest.mark.usefixtures("disable_skip_guard")
    def test_unexpected_md_error_propagates(self, tmp_path):
        """Verifies: a non-OSError raised by save_briefing_md (e.g. a
        programming bug surfacing as ValueError) is NOT swallowed and
        propagates to the caller.
        Why: blanket `except Exception` would hide real defects while still
        returning 200. The handler should only absorb expected filesystem
        failures (OSError family) and let other errors fail loudly.
        """
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p"),
            patch("src.handler.save_briefing_md", side_effect=ValueError("bug")),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            with pytest.raises(ValueError, match="bug"):
                briefing_handler()

    def test_notion_receives_model_footer(self, tmp_path):
        briefing_text = _VALID_BRIEFING
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=briefing_text),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p") as mock_notion,
            patch("src.handler.get_model", return_value="claude-haiku-4-5-20251001"),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            briefing_handler()
        expected_text = briefing_text + "\n\n---\nModel: claude-haiku-4-5-20251001"
        assert mock_notion.call_args[0][0] == expected_text

    @pytest.mark.usefixtures("disable_skip_guard")
    def test_hijacked_briefing_shape_raises_and_skips_delivery(self, tmp_path):
        """Verifies: when generate_briefing() returns text that doesn't look
        like a real briefing body (e.g. a skill self-firing mid-run and
        returning its own short completion report instead, #409), the
        handler raises before writing the local MD or delivering to
        Discord/Notion — it must not silently persist/deliver junk.
        """
        hijacked_text = (
            "本日分のページを新規作成し追記しました。\n\n"
            "- ローカル: `output/my-world-briefing_2026-07-21.md`\n"
            "- Notion: https://www.notion.so/3a36396b8c4e8172abcce57f9b706ce4"
        )
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=hijacked_text),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.save_briefing_md") as mock_save,
            patch("src.handler.send_to_discord") as mock_discord,
            patch("src.handler.send_to_notion") as mock_notion,
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            with pytest.raises(RuntimeError, match="does not look like a real briefing"):
                briefing_handler()

        mock_save.assert_not_called()
        mock_discord.assert_not_called()
        mock_notion.assert_not_called()

    @pytest.mark.usefixtures("disable_skip_guard")
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
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord") as mock_discord,
            patch("src.handler.send_to_notion") as mock_notion,
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = ""
            mock_cfg.discord_channel_id = ""
            mock_cfg.notion_api_key = ""
            mock_cfg.notion_database_id = ""
            result = briefing_handler()

        assert result["statusCode"] == 200
        assert result["md_written"] is True
        mock_discord.assert_not_called()
        mock_notion.assert_not_called()
        md_files = list(tmp_path.glob("briefing_*.md"))
        assert len(md_files) == 1

    def test_discord_only_writes_md_for_missing_notion(self, tmp_path):
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord") as mock_discord,
            patch("src.handler.send_to_notion") as mock_notion,
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = ""
            mock_cfg.notion_database_id = ""
            result = briefing_handler()

        assert result["statusCode"] == 200
        assert result["md_written"] is True
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

    def test_skips_when_md_exists_today(self, tmp_path):
        """Second run on the same day exits early without calling generate_briefing."""
        from datetime import date
        today_md = tmp_path / f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
        today_md.write_text("existing briefing")

        with (
            patch("src.handler.fetch_stock_moves") as mock_stocks,
            patch("src.handler.generate_briefing") as mock_gen,
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch("src.handler.BRIEFING_SKIP_IF_EXISTS", True),
        ):
            result = briefing_handler()

        assert result["statusCode"] == 200
        assert "skipped" in result["body"]
        mock_stocks.assert_not_called()
        mock_gen.assert_not_called()

    def test_force_flag_runs_despite_existing_md(self, tmp_path):
        """--force bypasses the idempotency guard even when today's MD exists."""
        from datetime import date
        today_md = tmp_path / f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
        today_md.write_text("existing briefing")

        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p"),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch("src.handler.BRIEFING_SKIP_IF_EXISTS", True),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            result = briefing_handler(force=True)

        assert result["statusCode"] == 200
        assert result["body"] != "skipped (already generated today)"

    def test_skip_guard_disabled_by_constant(self, tmp_path):
        """BRIEFING_SKIP_IF_EXISTS=False lets the pipeline run even if MD exists."""
        from datetime import date
        today_md = tmp_path / f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
        today_md.write_text("existing briefing")

        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p"),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch("src.handler.BRIEFING_SKIP_IF_EXISTS", False),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            result = briefing_handler()

        assert result["statusCode"] == 200
        assert "skipped" not in result["body"]

    def test_handler_forwards_rotation_enabled_to_save_briefing_md(self, tmp_path):
        """Verifies: BRIEFING_MD_ROTATION_ENABLED from constants is forwarded to save_briefing_md.
        Why: changing the constant must actually toggle rotation end-to-end.
        """
        captured = {}

        def fake_save(text, output_dir, retention_days, today=None, *, rotation_enabled=True):
            captured["rotation_enabled"] = rotation_enabled
            (output_dir / "briefing_2026-01-01.md").write_text(text)

        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.save_briefing_md", side_effect=fake_save),
            patch("src.handler.BRIEFING_MD_ROTATION_ENABLED", False),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = ""
            mock_cfg.discord_channel_id = ""
            mock_cfg.notion_api_key = ""
            mock_cfg.notion_database_id = ""
            briefing_handler()

        assert captured.get("rotation_enabled") is False

    def test_indexes_briefing_into_chromadb_after_successful_write(self, tmp_path):
        """Verifies: after a successful local MD write, the handler indexes
        it for cross-date chat RAG (#395).
        """
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p"),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch("src.handler.index_briefings") as mock_index,
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            briefing_handler()

        mock_index.assert_called_once()

    @pytest.mark.usefixtures("disable_skip_guard")
    def test_indexing_failure_does_not_block_briefing_delivery(self, tmp_path, caplog):
        """Verifies: an Ollama/Chroma failure during indexing is logged and
        swallowed — the daily batch's primary deliveries must not depend on
        the experimental local-LLM stack being available (degraded mode).
        """
        import logging

        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord") as mock_discord,
            patch("src.handler.send_to_notion", return_value="https://notion.so/p") as mock_notion,
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch("src.handler.index_briefings", side_effect=RuntimeError("ollama down")),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            with caplog.at_level(logging.WARNING, logger="src.handler"):
                result = briefing_handler()

        assert result["statusCode"] == 200
        mock_discord.assert_called_once()
        mock_notion.assert_called_once()
        assert any("indexing" in r.message for r in caplog.records)

    @pytest.mark.usefixtures("disable_skip_guard")
    def test_indexing_skipped_when_md_write_failed(self, tmp_path):
        """Verifies: indexing is not attempted when the local MD write itself
        failed — there is nothing new on disk to index.
        """
        with (
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p"),
            patch("src.handler.save_briefing_md", side_effect=OSError("disk full")),
            patch("src.handler.index_briefings") as mock_index,
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            briefing_handler()

        mock_index.assert_not_called()

    def test_preflight_warns_on_missing_discord(self, caplog):
        import logging
        with (
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.fetch_stock_moves", return_value="PLTR: ↑1.0%"),
            patch("src.handler.generate_briefing", return_value=_VALID_BRIEFING),
            patch("src.handler.get_model", return_value="claude-sonnet-4-6"),
            patch("src.handler.send_to_notion"),
            patch("src.handler.BRIEFING_OUTPUT_DIR", Path("/tmp")),
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
            patch("src.xss_handler.OUTPUT_DIR", tmp_path),
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
