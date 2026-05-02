"""週次ハンドラと Notion ページ取得のテスト。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from src.weekly_handler import weekly_handler
from src.notifier.notion import (
    _rich_text_to_str,
    _block_to_text,
    _extract_page_title,
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
        with pytest.raises(ValueError, match="見つかりませんでした"):
            generate_weekly_summary([])

    def test_calls_run_claude(self):
        pages = [{"date": "2026-04-25", "title": "T", "text": "content"}]
        with patch("src.generator.weekly_summary.run_claude", return_value="summary") as mock_run:
            result = generate_weekly_summary(pages)
        assert result == "summary"
        mock_run.assert_called_once()


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
# 統合テスト: weekly_handler
# ---------------------------------------------------------------------------

class TestWeeklyHandler:
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
