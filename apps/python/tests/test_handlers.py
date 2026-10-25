from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import HIJACKED_SKILL_COMPLETION_REPORT
from src.generator.briefscript_schema import BriefingDocument, MarkdownSection
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


# A generate_briefing_document() mock that renders to text must pass looks_like_briefing()
# (heading + minimum length, #409) or the handler raises before delivery.
_VALID_BRIEFING = "### ブリーフィング本文\n\n" + "本文です。" * 40


def _doc(text: str) -> BriefingDocument:
    """A generate_briefing_document() return value that renders to ``text``."""
    return BriefingDocument(date=date.today(), sections=[MarkdownSection(text=text)])


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


@pytest.fixture(autouse=True)
def stub_chart(tmp_path):
    """Keep the briefing's chart step off the network.

    ``step_chart`` calls yfinance, and every pipeline test in this module runs
    it. Autouse rather than per-test, so a test added later cannot silently
    reintroduce a live download.
    """
    png = tmp_path / "price-comparison-20260905.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    with patch("src.handler.generate_price_comparison", return_value=png):
        yield png


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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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

    def test_generate_receives_the_fetched_quotes_and_fx_move(self, tmp_path):
        """The holdings headings (#506) must use the same fetch as the prompt."""
        quotes = {"PLTR": object()}
        with (
            patch("src.handler.fetch_fx_context", return_value=("fx block", -0.9)),
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", quotes)) as snap,
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)) as gen,
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch("src.handler.BRIEFING_SKIP_IF_EXISTS", False),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = None
            mock_cfg.notion_database_id = None
            briefing_handler()
        snap.assert_called_once_with(["PLTR"], -0.9)
        args, kwargs = gen.call_args
        assert args[0] == "PLTR: ↑1.0%" and args[2] == "fx block"
        assert kwargs == {"quotes": quotes, "fx_change_pct": -0.9}

    def test_md_written_even_when_notifiers_succeed(self, tmp_path):
        """Verifies: when Discord/Notion both succeed, a local MD file is
        still written under BRIEFING_OUTPUT_DIR.
        Why: the new always-write requirement (issue #38). Operators need a
        local copy regardless of remote-notifier success.
        """
        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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

    def _run_persist(self, tmp_path, *extra):
        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.index_briefings"),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch("src.handler.BRIEFING_SKIP_IF_EXISTS", False),
            ExitStack() as stack,
        ):
            for p in extra:
                stack.enter_context(p)
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = mock_cfg.discord_channel_id = ""
            mock_cfg.notion_api_key = mock_cfg.notion_database_id = ""
            return briefing_handler()

    def test_briefing_ir_json_written_beside_the_md(self, tmp_path):
        """Verifies: the IR is persisted so renderers can re-run offline (#513)."""
        from src.generator.briefscript_render import render_document_markdown

        self._run_persist(tmp_path)
        (json_file,) = (tmp_path / "ir").glob("briefing_*.json")
        doc = BriefingDocument.model_validate_json(json_file.read_text(encoding="utf-8"))
        assert render_document_markdown(doc) == _VALID_BRIEFING

    def test_ir_json_failure_does_not_block_the_md(self, tmp_path):
        """Verifies: the JSON is secondary — an OSError writing it still leaves the MD."""
        result = self._run_persist(
            tmp_path, patch("src.handler.save_briefing_document", side_effect=OSError("disk full")),
        )
        assert result["md_written"] is True
        assert len(list(tmp_path.glob("briefing_*.md"))) == 1

    def test_md_written_even_when_discord_raises(self, tmp_path):
        """Verifies: when send_to_discord raises, the local MD file is still
        written before the exception propagates.
        Why: issue #38 specifies Discord/Notion/local MD as three independent
        outputs. A Discord outage must not prevent the local copy from being
        saved — that copy is the operator's diagnostic fallback.
        """
        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord") as mock_discord,
            patch("src.handler.send_to_notion", return_value="https://notion.so/p") as mock_notion,
            patch("src.handler.save_briefing_md", side_effect=OSError("disk full")),
            patch("src.handler.save_briefing_document"),
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
    def test_chart_is_attached_to_the_discord_delivery(self, tmp_path, stub_chart):
        """Verifies: the PNG produced by step_chart reaches send_to_discord.
        Why: the chart step exists only to put a picture in the Discord
        message — a rendered file nobody delivers is the bug this guards.
        """
        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord") as mock_discord,
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
        assert mock_discord.call_args.kwargs["attachment"] == str(stub_chart)

    @pytest.mark.usefixtures("disable_skip_guard")
    def test_chart_renders_without_discord(self, tmp_path, stub_chart):
        """Verifies: the chart still renders when Discord is unconfigured.
        Why: the dated PNG is its primary destination, and the maintainer's own
        setup delivers to Notion only. Gating the render on Discord skipped the
        feature entirely on exactly the machine it was built for.
        """
        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
            patch("src.handler.CONFIG", _no_api_config_mock()) as mock_cfg,
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch("src.handler.generate_price_comparison", return_value=stub_chart) as mock_chart,
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            result = briefing_handler()

        assert result["statusCode"] == 200
        mock_chart.assert_called_once()

    @pytest.mark.usefixtures("disable_skip_guard")
    def test_chart_failure_still_delivers_the_briefing(self, tmp_path):
        """Verifies: when the chart render raises, the run still succeeds and
        Discord is called with no attachment.
        Why: the chart is best_effort. A yfinance outage must cost the reader
        the picture, never the briefing — and a failed best-effort step records
        no result, so the delivery has to tolerate the key being absent.
        """
        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord") as mock_discord,
            patch("src.notifier.notion.Client", return_value=_notion_mock()),
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch(
                "src.handler.generate_price_comparison",
                side_effect=ValueError("no usable ticker data for chart"),
            ),
        ):
            mock_cfg.portfolio.tickers = ["PLTR"]
            mock_cfg.discord_token = "tok"
            mock_cfg.discord_channel_id = "ch"
            mock_cfg.notion_api_key = "key"
            mock_cfg.notion_database_id = "db"
            result = briefing_handler()

        assert result["statusCode"] == 200
        mock_discord.assert_called_once()
        assert mock_discord.call_args.kwargs["attachment"] is None

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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p"),
            patch("src.handler.save_briefing_md", side_effect=ValueError("bug")),
            patch("src.handler.save_briefing_document"),
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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(briefing_text)),
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
        # The page body is built from the IR (#516); a Markdown-only document
        # converts to the same blocks the text would.
        from src.notifier.markdown import markdown_to_notion_blocks

        assert mock_notion.call_args.kwargs["blocks"] == markdown_to_notion_blocks(expected_text)
        assert mock_notion.call_count == 1


class TestDeliverNotionFallback:
    """step_deliver_notion retries with the Markdown conversion (#516)."""

    def _run(self, results):
        from src.handler import step_deliver_notion

        ctx = MagicMock()
        ctx.results = {"generate": _doc(_VALID_BRIEFING)}
        with (
            patch("src.handler.CONFIG") as cfg,
            patch("src.handler.send_to_notion", side_effect=results) as notion,
            patch("src.handler.get_model", return_value="m"),
        ):
            cfg.portfolio.tickers = ["PLTR"]
            url = step_deliver_notion(ctx)
        return url, notion

    def test_rejected_ir_blocks_fall_back_to_markdown(self):
        url, notion = self._run(["", "https://notion.so/p"])
        assert url == "https://notion.so/p"
        first, second = notion.call_args_list
        assert "blocks" in first.kwargs and "blocks" not in second.kwargs
        # Strict, so a rejected batch past the first 100 also triggers the retry.
        assert first.kwargs["strict"] is True and "strict" not in second.kwargs
        assert second.args[0] == first.args[0]
        assert second.kwargs["title"] == first.kwargs["title"]

    def test_success_does_not_retry(self):
        url, notion = self._run(["https://notion.so/p"])
        assert url == "https://notion.so/p" and notion.call_count == 1

    def test_both_failing_returns_empty(self):
        url, notion = self._run(["", ""])
        assert url == "" and notion.call_count == 2

    @pytest.mark.usefixtures("disable_skip_guard")
    def test_hijacked_briefing_shape_raises_and_skips_delivery(self, tmp_path):
        """Verifies: when generate_briefing_document() renders text that doesn't look
        like a real briefing body (e.g. a skill self-firing mid-run and
        returning its own short completion report instead, #409), the
        handler raises before writing the local MD or delivering to
        Discord/Notion — it must not silently persist/deliver junk.
        """
        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(HIJACKED_SKILL_COMPLETION_REPORT)),
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
            with pytest.raises(RuntimeError, match="does not look like a real briefing") as exc_info:
                briefing_handler()

        mock_save.assert_not_called()
        mock_discord.assert_not_called()
        mock_notion.assert_not_called()
        # The raw (potentially sensitive, e.g. portfolio/financial) briefing
        # text must never land in an exception message that could be logged
        # or sent to a monitoring service (review feedback on #410).
        assert "notion.so" not in str(exc_info.value)
        assert "my-world-briefing" not in str(exc_info.value)

    @pytest.mark.usefixtures("disable_skip_guard")
    def test_briefing_failure_propagates(self):
        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", side_effect=RuntimeError("claude error")),
            patch("src.handler.send_to_discord"),
        ):
            with pytest.raises(RuntimeError, match="claude error"):
                briefing_handler()

    def test_no_credentials_writes_md_and_skips_notifiers(self, tmp_path):
        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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
            patch("src.handler.fetch_stock_snapshot") as mock_stocks,
            patch("src.handler.generate_briefing_document") as mock_gen,
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
        """Second run on the same day exits early without calling generate_briefing_document."""
        from datetime import date
        today_md = tmp_path / f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
        today_md.write_text("existing briefing")

        with (
            patch("src.handler.fetch_stock_snapshot") as mock_stocks,
            patch("src.handler.generate_briefing_document") as mock_gen,
            patch("src.handler.BRIEFING_OUTPUT_DIR", tmp_path),
            patch("src.handler.BRIEFING_SKIP_IF_EXISTS", True),
        ):
            result = briefing_handler()

        assert result["statusCode"] == 200
        assert "skipped" in result["body"]
        mock_stocks.assert_not_called()
        mock_gen.assert_not_called()

    def test_does_not_skip_when_todays_md_is_degraded(self, tmp_path):
        """A degraded briefing must not block a retry for the rest of the day.

        The skip guard exists to stop duplicate *successful* runs. Once a
        half-failed body counts as "today's briefing", the normal recovery path
        (press Run again — the web route never passes force) would answer
        "skipped" and the full briefing becomes unobtainable until tomorrow.
        """
        from datetime import date
        today_md = tmp_path / f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
        today_md.write_text(
            "⚠️ メイン分析の取得に失敗しました。セクター動向のみお届けします。\n"
            "claude CLI timed out (メイン分析)\n\n---\n\n## セクター動向\n\n### 今日のセクター動向\n"
            + "セクター本文。" * 40
        )

        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)) as mock_gen,
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
            result = briefing_handler()

        assert result["statusCode"] == 200
        assert "skipped" not in result["body"]
        mock_gen.assert_called_once()

    def test_force_flag_runs_despite_existing_md(self, tmp_path):
        """--force bypasses the idempotency guard even when today's MD exists."""
        from datetime import date
        today_md = tmp_path / f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
        today_md.write_text("existing briefing")

        with (
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.save_briefing_md", side_effect=fake_save),
            patch("src.handler.save_briefing_document"),
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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
            patch("src.handler.CONFIG") as mock_cfg,
            patch("src.handler.send_to_discord"),
            patch("src.handler.send_to_notion", return_value="https://notion.so/p"),
            patch("src.handler.save_briefing_md", side_effect=OSError("disk full")),
            patch("src.handler.save_briefing_document"),
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
            patch("src.handler.fetch_stock_snapshot", return_value=("PLTR: ↑1.0%", {})),
            patch("src.handler.generate_briefing_document", return_value=_doc(_VALID_BRIEFING)),
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
