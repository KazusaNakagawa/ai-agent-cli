"""週次ハンドラと Notion ページ取得のテスト。"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from src.weekly_handler import weekly_handler
from src.notifier.notion import (
    _rich_text_to_str,
    _block_to_text,
    _extract_page_title,
    fetch_commentable_pages,
    fetch_new_comments,
    fetch_weekly_pages,
)
from src.generator.weekly_summary import _format_briefings, week_label, generate_weekly_summary

# テスト内で固定する「現在時刻」: ページ日付 2026-04-25 が days=7 の範囲内に収まる値
_FIXED_NOW = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# ユニットテスト: ヘルパー関数
# ---------------------------------------------------------------------------

class TestRichTextToStr:
    def test_plain_text(self):
        rt = [{"text": {"content": "hello"}}]
        assert _rich_text_to_str(rt) == "hello"

    def test_multiple_chunks(self):
        rt = [{"text": {"content": "foo"}}, {"text": {"content": "bar"}}]
        assert _rich_text_to_str(rt) == "foobar"

    def test_empty(self):
        assert _rich_text_to_str([]) == ""


class TestBlockToText:
    def _make_block(self, block_type: str, text: str) -> dict:
        return {
            "type": block_type,
            block_type: {"rich_text": [{"text": {"content": text}}]},
        }

    def test_heading_1(self):
        assert _block_to_text(self._make_block("heading_1", "Title")) == "# Title"

    def test_heading_2(self):
        assert _block_to_text(self._make_block("heading_2", "Sub")) == "## Sub"

    def test_heading_3(self):
        assert _block_to_text(self._make_block("heading_3", "Sub2")) == "### Sub2"

    def test_bulleted_list(self):
        assert _block_to_text(self._make_block("bulleted_list_item", "item")) == "- item"

    def test_numbered_list(self):
        assert _block_to_text(self._make_block("numbered_list_item", "item")) == "1. item"

    def test_divider(self):
        block = {"type": "divider", "divider": {}}
        assert _block_to_text(block) == "---"

    def test_paragraph(self):
        assert _block_to_text(self._make_block("paragraph", "text")) == "text"

    def test_table_row(self):
        block = {
            "type": "table_row",
            "table_row": {"cells": [
                [{"text": {"content": "A"}}],
                [{"text": {"content": "B"}}],
            ]},
        }
        assert _block_to_text(block) == "| A | B |"


class TestExtractPageTitle:
    def test_title_property(self):
        page = {
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"text": {"content": "My Page"}}],
                }
            }
        }
        assert _extract_page_title(page) == "My Page"

    def test_no_title_property(self):
        page = {"properties": {}}
        assert _extract_page_title(page) == "(無題)"


# ---------------------------------------------------------------------------
# ユニットテスト: weekly_summary ジェネレータ
# ---------------------------------------------------------------------------

class TestFormatBriefings:
    def test_single_page(self):
        pages = [{"date": "2026-04-25", "title": "テスト", "text": "内容"}]
        result = _format_briefings(pages)
        assert "2026-04-25" in result
        assert "テスト" in result
        assert "内容" in result

    def test_multiple_pages_separated(self):
        pages = [
            {"date": "2026-04-24", "title": "A", "text": "textA"},
            {"date": "2026-04-25", "title": "B", "text": "textB"},
        ]
        result = _format_briefings(pages)
        assert "---" in result
        assert "textA" in result
        assert "textB" in result


class TestGenerateWeeklySummary:
    def test_empty_pages_raises(self):
        with pytest.raises(ValueError, match="no pages found"):
            generate_weekly_summary([])

    def test_delegates_to_run_claude(self):
        """週次サマリーは run_claude 経路に委譲し、プロンプトにページ本文と purpose が含まれる。"""
        pages = [{"date": "2026-04-25", "title": "T", "text": "content"}]

        with patch(
            "src.generator.weekly_summary.run_claude",
            return_value="週次サマリー本文",
        ) as mock_run:
            result = generate_weekly_summary(pages)

        assert result == "週次サマリー本文"
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        prompt_arg, purpose_arg = args[:2]
        assert "content" in prompt_arg
        assert purpose_arg == "週次サマリー生成"

    def test_run_claude_receives_timeout(self):
        """run_claude に TIMEOUT_WEEKLY_SUMMARY が timeout キーワードで渡される。"""
        from src.constants import TIMEOUT_WEEKLY_SUMMARY

        pages = [{"date": "2026-04-25", "title": "T", "text": "content"}]

        with patch(
            "src.generator.weekly_summary.run_claude",
            return_value="summary",
        ) as mock_run:
            generate_weekly_summary(pages)

        _, call_kwargs = mock_run.call_args
        # timeout is the 3rd positional arg; accept both positional and keyword form
        timeout_val = call_kwargs.get("timeout", mock_run.call_args.args[2] if len(mock_run.call_args.args) > 2 else None)
        assert timeout_val == TIMEOUT_WEEKLY_SUMMARY


# ---------------------------------------------------------------------------
# 統合テスト: fetch_weekly_pages
# ---------------------------------------------------------------------------

def _make_notion_client_mock(pages_data: list[dict], blocks_data: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.search.return_value = {"results": pages_data, "has_more": False}
    mock.blocks.children.list.return_value = {"results": blocks_data, "has_more": False}
    return mock


class TestFetchWeeklyPages:
    def _make_page(self, title: str, created: str, db_id: str = "db-id", tags: list[str] | None = None) -> dict:
        return {
            "id": "page-id",
            "created_time": created,
            "parent": {"type": "database_id", "database_id": db_id},
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"text": {"content": title}}],
                },
                "Tags": {
                    "type": "multi_select",
                    "multi_select": [{"name": t} for t in (tags or ["agent"])],
                },
            },
        }

    def test_returns_pages(self):
        page = self._make_page("ブリーフィング", "2026-04-25T00:00:00.000Z")
        notion_mock = _make_notion_client_mock(
            pages_data=[page],
            blocks_data=[{
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": "本文"}}]},
            }],
        )
        with (
            patch("src.notifier.notion.Client", return_value=notion_mock),
            patch("src.notifier.notion._utcnow", return_value=_FIXED_NOW),
        ):
            result = fetch_weekly_pages("key", "db-id", days=7)

        assert len(result) == 1
        assert result[0]["title"] == "ブリーフィング"
        assert result[0]["date"] == "2026-04-25"
        assert result[0]["text"] == "本文"
        assert result[0]["page_id"] == "page-id"

    def test_empty_credentials_returns_empty(self):
        assert fetch_weekly_pages("", "db-id") == []
        assert fetch_weekly_pages("key", "") == []

    def test_filters_by_tag(self):
        """agent タグのないページは除外される"""
        page_agent = self._make_page("briefing", "2026-04-25T00:00:00.000Z", tags=["agent"])
        page_xss = self._make_page("xss", "2026-04-25T00:00:00.000Z", tags=["xss"])
        notion_mock = _make_notion_client_mock(
            pages_data=[page_agent, page_xss],
            blocks_data=[],
        )
        with (
            patch("src.notifier.notion.Client", return_value=notion_mock),
            patch("src.notifier.notion._utcnow", return_value=_FIXED_NOW),
        ):
            result = fetch_weekly_pages("key", "db-id", days=7)
        assert len(result) == 1
        assert result[0]["title"] == "briefing"

    def test_api_error_returns_empty(self):
        notion_mock = MagicMock()
        notion_mock.search.side_effect = Exception("API error")
        with patch("src.notifier.notion.Client", return_value=notion_mock):
            result = fetch_weekly_pages("key", "db-id")
        assert result == []

    def test_z_suffix_timestamp_included(self):
        """Notion の Z サフィックス付き created_time が正しく比較されること。"""
        page = self._make_page("new", "2026-04-25T00:00:00.000Z")
        notion_mock = _make_notion_client_mock(pages_data=[page], blocks_data=[])
        with (
            patch("src.notifier.notion.Client", return_value=notion_mock),
            patch("src.notifier.notion._utcnow", return_value=_FIXED_NOW),
        ):
            result = fetch_weekly_pages("key", "db-id", days=7)
        assert len(result) == 1

    def test_old_page_excluded_by_datetime(self):
        """days 範囲外のページは除外されること。"""
        page = self._make_page("old", "2020-01-01T00:00:00.000Z")
        notion_mock = _make_notion_client_mock(pages_data=[page], blocks_data=[])
        with patch("src.notifier.notion.Client", return_value=notion_mock):
            result = fetch_weekly_pages("key", "db-id", days=7)
        assert result == []


# ---------------------------------------------------------------------------
# 統合テスト: fetch_commentable_pages (#396)
# ---------------------------------------------------------------------------

def _make_page_with_edit(
    title: str, created: str, edited: str, db_id: str = "db-id",
    tags: list[str] | None = None, page_id: str = "page-id",
) -> dict:
    return {
        "id": page_id,
        "created_time": created,
        "last_edited_time": edited,
        "parent": {"type": "database_id", "database_id": db_id},
        "properties": {
            "Name": {"type": "title", "title": [{"text": {"content": title}}]},
            "Tags": {"type": "multi_select", "multi_select": [{"name": t} for t in (tags or ["agent"])]},
        },
    }


class TestFetchCommentablePages:
    def test_returns_page_id_title_date(self):
        page = _make_page_with_edit(
            "ブリーフィング", "2026-04-01T00:00:00.000Z", "2026-04-25T00:00:00.000Z",
            page_id="the-page-id",
        )
        notion_mock = MagicMock()
        notion_mock.search.return_value = {"results": [page], "has_more": False}
        with (
            patch("src.notifier.notion.Client", return_value=notion_mock),
            patch("src.notifier.notion._utcnow", return_value=_FIXED_NOW),
        ):
            result = fetch_commentable_pages("key", "db-id", days=7)
        assert result == [{"page_id": "the-page-id", "title": "ブリーフィング", "date": "2026-04-01"}]

    def test_old_creation_but_recent_edit_is_included(self):
        """A page created long ago but edited (e.g. commented on) this week
        must still surface — unlike fetch_weekly_pages, which only looks at
        created_time and would miss it (#396)."""
        page = _make_page_with_edit(
            "old briefing", "2020-01-01T00:00:00.000Z", "2026-04-25T00:00:00.000Z",
        )
        notion_mock = MagicMock()
        notion_mock.search.return_value = {"results": [page], "has_more": False}
        with (
            patch("src.notifier.notion.Client", return_value=notion_mock),
            patch("src.notifier.notion._utcnow", return_value=_FIXED_NOW),
        ):
            result = fetch_commentable_pages("key", "db-id", days=7)
        assert len(result) == 1

    def test_recently_created_but_stale_edit_is_excluded(self):
        page = _make_page_with_edit(
            "stale", "2026-04-25T00:00:00.000Z", "2020-01-01T00:00:00.000Z",
        )
        notion_mock = MagicMock()
        notion_mock.search.return_value = {"results": [page], "has_more": False}
        with (
            patch("src.notifier.notion.Client", return_value=notion_mock),
            patch("src.notifier.notion._utcnow", return_value=_FIXED_NOW),
        ):
            result = fetch_commentable_pages("key", "db-id", days=7)
        assert result == []

    def test_filters_by_tag(self):
        page_agent = _make_page_with_edit(
            "agent", "2026-04-01T00:00:00.000Z", "2026-04-25T00:00:00.000Z", tags=["agent"],
        )
        page_xss = _make_page_with_edit(
            "xss", "2026-04-01T00:00:00.000Z", "2026-04-25T00:00:00.000Z", tags=["xss"],
        )
        notion_mock = MagicMock()
        notion_mock.search.return_value = {"results": [page_agent, page_xss], "has_more": False}
        with (
            patch("src.notifier.notion.Client", return_value=notion_mock),
            patch("src.notifier.notion._utcnow", return_value=_FIXED_NOW),
        ):
            result = fetch_commentable_pages("key", "db-id", days=7)
        assert len(result) == 1
        assert result[0]["title"] == "agent"

    def test_empty_credentials_returns_empty(self):
        assert fetch_commentable_pages("", "db-id") == []
        assert fetch_commentable_pages("key", "") == []

    def test_api_error_returns_empty(self):
        notion_mock = MagicMock()
        notion_mock.search.side_effect = Exception("API error")
        with patch("src.notifier.notion.Client", return_value=notion_mock):
            result = fetch_commentable_pages("key", "db-id")
        assert result == []


# ---------------------------------------------------------------------------
# 統合テスト: fetch_new_comments (#396)
# ---------------------------------------------------------------------------

class TestFetchNewComments:
    def _pages(self):
        return [{"page_id": "p1", "title": "ブリーフィング — 2026-04-25", "date": "2026-04-25"}]

    def _comment(self, comment_id: str, text: str, created: str = "2026-04-25T10:00:00.000Z") -> dict:
        return {
            "id": comment_id,
            "created_time": created,
            "rich_text": [{"text": {"content": text}}],
        }

    def test_returns_new_comment_with_page_context(self):
        notion_mock = MagicMock()
        notion_mock.comments.list.return_value = {
            "results": [self._comment("c1", "この分析はおかしい")], "has_more": False,
        }
        with patch("src.notifier.notion.Client", return_value=notion_mock):
            result = fetch_new_comments("key", self._pages(), seen_ids=set())

        assert result == [{
            "comment_id": "c1",
            "page_id": "p1",
            "page_title": "ブリーフィング — 2026-04-25",
            "page_date": "2026-04-25",
            "text": "この分析はおかしい",
            "created_time": "2026-04-25T10:00:00.000Z",
        }]
        notion_mock.comments.list.assert_called_with(block_id="p1")

    def test_already_seen_comment_is_skipped(self):
        notion_mock = MagicMock()
        notion_mock.comments.list.return_value = {
            "results": [self._comment("c1", "既知のコメント")], "has_more": False,
        }
        with patch("src.notifier.notion.Client", return_value=notion_mock):
            result = fetch_new_comments("key", self._pages(), seen_ids={"c1"})
        assert result == []

    def test_blank_comment_text_is_skipped(self):
        notion_mock = MagicMock()
        notion_mock.comments.list.return_value = {
            "results": [self._comment("c1", "   ")], "has_more": False,
        }
        with patch("src.notifier.notion.Client", return_value=notion_mock):
            result = fetch_new_comments("key", self._pages(), seen_ids=set())
        assert result == []

    def test_one_page_comment_fetch_failure_does_not_block_others(self):
        notion_mock = MagicMock()
        notion_mock.comments.list.side_effect = [
            Exception("boom"),
            {"results": [self._comment("c2", "ok")], "has_more": False},
        ]
        pages = [
            {"page_id": "p1", "title": "a", "date": "2026-04-24"},
            {"page_id": "p2", "title": "b", "date": "2026-04-25"},
        ]
        with patch("src.notifier.notion.Client", return_value=notion_mock):
            result = fetch_new_comments("key", pages, seen_ids=set())
        assert len(result) == 1
        assert result[0]["comment_id"] == "c2"

    def test_empty_inputs_return_empty(self):
        assert fetch_new_comments("", self._pages(), seen_ids=set()) == []
        assert fetch_new_comments("key", [], seen_ids=set()) == []


# ---------------------------------------------------------------------------
# 統合テスト: weekly_handler
# ---------------------------------------------------------------------------

class TestWeeklyHandler:
    @pytest.fixture(autouse=True)
    def _isolate_output_dir(self, tmp_path):
        """Redirect local MD writes to tmp_path so tests never touch the repo's output dir."""
        with patch("src.weekly_handler.BRIEFING_OUTPUT_DIR", tmp_path):
            self._out_dir = tmp_path
            yield

    @pytest.fixture(autouse=True)
    def _disable_comment_ingestion_by_default(self):
        """Comment ingestion (#396) is opt-in per test. The real
        judge_available() would find the CLI on this developer's machine
        (~/work/dotfiles-claude/bin/judge), so force it off here and let the
        dedicated TestIngestNotionComments tests re-enable it explicitly."""
        with patch("src.weekly_handler.judgment_ingest.judge_available", return_value=False):
            yield

    def test_success_returns_200(self):
        pages = [{"date": "2026-04-25", "title": "T", "text": "content"}]
        with (
            patch("src.weekly_handler.fetch_weekly_pages", return_value=pages),
            patch("src.weekly_handler.generate_weekly_summary", return_value="サマリー"),
            patch("src.weekly_handler.send_to_notion", return_value="https://notion.so/weekly"),
        ):
            result = weekly_handler()
        assert result["statusCode"] == 200

    def test_no_pages_returns_204(self):
        with patch("src.weekly_handler.fetch_weekly_pages", return_value=[]):
            result = weekly_handler()
        assert result["statusCode"] == 204

    def test_summary_generation_failure_propagates(self):
        pages = [{"date": "2026-04-25", "title": "T", "text": "content"}]
        with (
            patch("src.weekly_handler.fetch_weekly_pages", return_value=pages),
            patch("src.weekly_handler.generate_weekly_summary", side_effect=RuntimeError("fail")),
        ):
            with pytest.raises(RuntimeError, match="fail"):
                weekly_handler()

    def test_notion_post_failure_returns_500(self):
        pages = [{"date": "2026-04-25", "title": "T", "text": "content"}]
        with (
            patch("src.weekly_handler.fetch_weekly_pages", return_value=pages),
            patch("src.weekly_handler.generate_weekly_summary", return_value="サマリー"),
            patch("src.weekly_handler.send_to_notion", return_value=""),
        ):
            result = weekly_handler()
        assert result["statusCode"] == 500

    def test_saves_local_weekly_md(self):
        """The recap is written locally as weekly-summary_<date>.md for the Briefing viewer."""
        pages = [{"date": "2026-04-25", "title": "T", "text": "content"}]
        with (
            patch("src.weekly_handler.fetch_weekly_pages", return_value=pages),
            patch("src.weekly_handler.generate_weekly_summary", return_value="サマリー本文"),
            patch("src.weekly_handler.send_to_notion", return_value="https://notion.so/w"),
        ):
            weekly_handler()

        expected = f"weekly-summary_{date.today().strftime('%Y-%m-%d')}.md"
        written = list(self._out_dir.glob("weekly-summary_*.md"))
        assert len(written) == 1
        assert written[0].name == expected
        assert written[0].read_text(encoding="utf-8") == "サマリー本文"

    def test_notion_post_includes_weekly_tag(self):
        pages = [{"date": "2026-04-25", "title": "T", "text": "content"}]
        with (
            patch("src.weekly_handler.fetch_weekly_pages", return_value=pages),
            patch("src.weekly_handler.generate_weekly_summary", return_value="サマリー"),
            patch("src.weekly_handler.send_to_notion", return_value="https://notion.so/w") as mock_send,
        ):
            weekly_handler()

        _, kwargs = mock_send.call_args
        assert "weekly-summary" in kwargs["tags"]

    def test_comment_ingestion_failure_does_not_fail_the_response(self):
        """Degraded mode (#396): a crash in comment ingestion must not turn a
        successful weekly recap into a failure — same philosophy as the
        local-LLM briefing-indexing hook in src.handler."""
        pages = [{"date": "2026-04-25", "title": "T", "text": "content"}]
        with (
            patch("src.weekly_handler.fetch_weekly_pages", return_value=pages),
            patch("src.weekly_handler.generate_weekly_summary", return_value="サマリー"),
            patch("src.weekly_handler.send_to_notion", return_value="https://notion.so/w"),
            patch("src.weekly_handler._ingest_notion_comments", side_effect=RuntimeError("boom")),
        ):
            result = weekly_handler()
        assert result["statusCode"] == 200


# ---------------------------------------------------------------------------
# 統合テスト: _ingest_notion_comments (#396)
# ---------------------------------------------------------------------------

class TestIngestNotionComments:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path):
        with (
            patch("src.weekly_handler.notion_comment_state.STATE_FILE", tmp_path / "ids.json"),
            patch("src.weekly_handler.judgment_ingest.judge_available", return_value=True),
        ):
            yield

    def _comment(self, comment_id: str) -> dict:
        return {
            "comment_id": comment_id,
            "page_id": "p1",
            "page_title": "T",
            "page_date": "2026-04-25",
            "text": f"comment {comment_id}",
            "created_time": "2026-04-25T10:00:00.000Z",
        }

    def test_skips_when_judge_unavailable(self):
        with (
            patch("src.weekly_handler.judgment_ingest.judge_available", return_value=False),
            patch("src.weekly_handler.fetch_commentable_pages") as mock_pages,
        ):
            from src.weekly_handler import _ingest_notion_comments
            _ingest_notion_comments()
        mock_pages.assert_not_called()

    def test_skips_when_no_commentable_pages(self):
        with (
            patch("src.weekly_handler.fetch_commentable_pages", return_value=[]),
            patch("src.weekly_handler.fetch_new_comments") as mock_comments,
        ):
            from src.weekly_handler import _ingest_notion_comments
            _ingest_notion_comments()
        mock_comments.assert_not_called()

    def test_records_new_comments_and_persists_ids(self):
        from src import notion_comment_state
        from src.weekly_handler import _ingest_notion_comments

        pages = [{"page_id": "p1", "title": "T", "date": "2026-04-25"}]
        with (
            patch("src.weekly_handler.fetch_commentable_pages", return_value=pages),
            patch("src.weekly_handler.fetch_new_comments", return_value=[self._comment("c1"), self._comment("c2")]),
            patch("src.weekly_handler.judgment_ingest.record_comment_as_judgment", return_value=True) as mock_record,
        ):
            _ingest_notion_comments()

        assert mock_record.call_count == 2
        assert notion_comment_state.read_seen_ids() == {"c1", "c2"}

    def test_passes_previously_seen_ids_to_fetch_new_comments(self):
        from src import notion_comment_state
        from src.weekly_handler import _ingest_notion_comments

        notion_comment_state.write_seen_ids({"old-1"})
        pages = [{"page_id": "p1", "title": "T", "date": "2026-04-25"}]
        with (
            patch("src.weekly_handler.fetch_commentable_pages", return_value=pages),
            patch("src.weekly_handler.fetch_new_comments", return_value=[]) as mock_comments,
        ):
            _ingest_notion_comments()

        _, kwargs = mock_comments.call_args
        args = mock_comments.call_args.args
        seen_ids_arg = kwargs.get("seen_ids", args[2] if len(args) > 2 else None)
        assert seen_ids_arg == {"old-1"}

    def test_only_successfully_recorded_comments_are_marked_seen(self):
        """A judge-CLI failure on one comment must not mark it as ingested —
        otherwise it would be silently dropped forever instead of retried."""
        from src import notion_comment_state
        from src.weekly_handler import _ingest_notion_comments

        pages = [{"page_id": "p1", "title": "T", "date": "2026-04-25"}]
        with (
            patch("src.weekly_handler.fetch_commentable_pages", return_value=pages),
            patch("src.weekly_handler.fetch_new_comments", return_value=[self._comment("c1"), self._comment("c2")]),
            patch(
                "src.weekly_handler.judgment_ingest.record_comment_as_judgment",
                side_effect=[True, False],
            ),
        ):
            _ingest_notion_comments()

        assert notion_comment_state.read_seen_ids() == {"c1"}

    def test_no_state_write_when_nothing_new(self):
        from src import notion_comment_state
        from src.weekly_handler import _ingest_notion_comments

        pages = [{"page_id": "p1", "title": "T", "date": "2026-04-25"}]
        with (
            patch("src.weekly_handler.fetch_commentable_pages", return_value=pages),
            patch("src.weekly_handler.fetch_new_comments", return_value=[]),
            patch("src.weekly_handler.notion_comment_state.write_seen_ids") as mock_write,
        ):
            _ingest_notion_comments()
        mock_write.assert_not_called()
