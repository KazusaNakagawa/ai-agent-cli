from contextlib import ExitStack
from datetime import date
from unittest.mock import patch

from src.generator.briefing import SECTORS_FAILED_NOTICE
from src.recovery_handler import recover_sectors

_RECOVERED = "### 半導体\n" + "セクター本文。" * 40


def _degraded_body() -> str:
    return (
        "### 本日の相場\n" + "メイン本文。" * 40 + "\n\n---\n\n"
        f"{SECTORS_FAILED_NOTICE}\n"
        "claude CLI error [セクタースイープ] rc=1: Connection closed mid-response"
    )


def _write_today(tmp_path, body: str):
    path = tmp_path / f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _run(tmp_path, *, awake=True, sectors=_RECOVERED, notion=True):
    """Run recover_sectors with every external edge mocked."""
    stack = ExitStack()
    mocks = {}
    with stack:
        stack.enter_context(patch("src.recovery_handler.BRIEFING_OUTPUT_DIR", tmp_path))
        mocks["awake"] = stack.enter_context(
            patch("src.recovery_handler.is_system_awake", return_value=awake))
        mocks["generate"] = stack.enter_context(
            patch("src.recovery_handler.generate_sectors", return_value=sectors))
        mocks["append"] = stack.enter_context(
            patch("src.recovery_handler.append_to_page_by_title", return_value="https://notion.so/p"))
        stack.enter_context(patch("src.recovery_handler.fetch_stock_moves", return_value="PLTR: +2%"))
        stack.enter_context(patch("src.recovery_handler.fetch_fx_context", return_value=("", 0.0)))
        # Pinned rather than inherited from CONFIG: a developer's .env supplies
        # real Notion credentials while CI has none, so the assertions about
        # whether the append runs would otherwise flip between environments.
        stack.enter_context(patch("src.recovery_handler._is_configured", return_value=notion))
        result = recover_sectors()
    return result, mocks


class TestNothingToRecover:
    def test_missing_todays_briefing_is_a_no_op(self, tmp_path):
        result, mocks = _run(tmp_path)

        assert result["body"] == "skipped (no briefing today)"
        mocks["generate"].assert_not_called()

    def test_complete_briefing_is_a_no_op(self, tmp_path):
        _write_today(tmp_path, "### 本日の相場\n本文\n\n---\n\n## セクター動向\n\n### 半導体\n強い")

        result, mocks = _run(tmp_path)

        assert result["body"] == "skipped (sectors already present)"
        mocks["generate"].assert_not_called()


class TestDarkWakeGuard:
    def test_dark_wake_skips_before_spending_on_the_sweep(self, tmp_path):
        """The whole point of the job: a DarkWake run would be severed again,
        so it must not pay for a sweep that cannot finish."""
        path = _write_today(tmp_path, _degraded_body())

        result, mocks = _run(tmp_path, awake=False)

        assert result["body"] == "skipped (system not fully awake)"
        mocks["generate"].assert_not_called()
        assert SECTORS_FAILED_NOTICE in path.read_text(encoding="utf-8")


class TestSuccessfulRecovery:
    def test_replaces_the_failure_notice_in_todays_md(self, tmp_path):
        path = _write_today(tmp_path, _degraded_body())

        result, _ = _run(tmp_path)

        recovered = path.read_text(encoding="utf-8")
        assert result["statusCode"] == 200
        assert result["body"] == "sectors recovered"
        assert SECTORS_FAILED_NOTICE not in recovered
        assert "メイン本文。" in recovered
        assert "### 半導体" in recovered

    def test_appends_to_todays_notion_page(self, tmp_path):
        _write_today(tmp_path, _degraded_body())

        _, mocks = _run(tmp_path)

        _, kwargs = mocks["append"].call_args
        assert kwargs["title"] == f"マーケットブリーフィング — {date.today().strftime('%Y-%m-%d')}"
        assert "### 半導体" in mocks["append"].call_args[0][0]

    def test_recovery_is_idempotent(self, tmp_path):
        """A second run finds no failure notice and must not pay again."""
        _write_today(tmp_path, _degraded_body())
        _run(tmp_path)

        result, mocks = _run(tmp_path)

        assert result["body"] == "skipped (sectors already present)"
        mocks["generate"].assert_not_called()

    def test_notion_skipped_when_unconfigured(self, tmp_path):
        path = _write_today(tmp_path, _degraded_body())

        result, mocks = _run(tmp_path, notion=False)

        assert result["body"] == "sectors recovered"
        mocks["append"].assert_not_called()
        assert SECTORS_FAILED_NOTICE not in path.read_text(encoding="utf-8")


class TestBadSweepOutput:
    def test_junk_sweep_output_leaves_the_md_untouched(self, tmp_path):
        """A hijacked-skill report or truncated stub must not overwrite the
        briefing with junk — same guard philosophy as looks_like_briefing."""
        path = _write_today(tmp_path, _degraded_body())

        result, mocks = _run(tmp_path, sectors="完了しました。")

        assert result["body"] == "skipped (recovered sweep looks empty)"
        assert SECTORS_FAILED_NOTICE in path.read_text(encoding="utf-8")
        mocks["append"].assert_not_called()
