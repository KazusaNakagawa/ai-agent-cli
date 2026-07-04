"""Tests for Journal <-> Notion sync (docs/superpowers/specs/2026-07-03-journal-notion-sync-design.md).

Contract:
- New entry -> Notion page created; its id is saved as ``notion_page_id``.
- Append to an entry with a saved ``notion_page_id`` -> blocks appended to that page.
- Append to an entry without one (pre-sync entry) -> falls back to creating a page.
- Notion failures are best-effort: the local journal write always succeeds.
- Title is derived from the entry's first line (heading/list markers stripped,
  truncated to 60 chars, falls back to the entry's date when empty).
"""
from unittest.mock import MagicMock, patch

import pytest

from src import journal_store
from src.notifier import journal_sync


def _make_notion_mock(title_prop="Name", page_id="page-1"):
    mock = MagicMock()
    mock.databases.retrieve.return_value = {
        "properties": {title_prop: {"type": "title"}}
    }
    mock.pages.create.return_value = {"id": page_id, "url": f"https://notion.so/{page_id}"}
    return mock


@pytest.fixture
def mock_notion():
    with patch("src.notifier.journal_sync.Client") as MockClient:
        notion = _make_notion_mock()
        MockClient.return_value = notion
        yield notion


class TestTitleFromContent:
    def test_uses_first_line(self):
        assert journal_sync.title_from_content("hello world\nmore", "2026-07-03") == "hello world"

    def test_strips_heading_marker(self):
        assert journal_sync.title_from_content("### Heading\nbody", "2026-07-03") == "Heading"

    def test_strips_list_marker(self):
        assert journal_sync.title_from_content("- item one", "2026-07-03") == "item one"

    def test_falls_back_to_date_when_empty(self):
        assert journal_sync.title_from_content("### \n\n", "2026-07-03") == "2026-07-03"

    def test_truncated_to_60_chars(self):
        long_line = "a" * 100
        result = journal_sync.title_from_content(long_line, "2026-07-03")
        assert len(result) == 60

    def test_skips_leading_blank_lines(self):
        assert journal_sync.title_from_content("\n\nfirst real line", "2026-07-03") == "first real line"


class TestSyncNewEntry:
    def test_no_credentials_no_op(self, journal_dir):
        entry_id = journal_store.append_entry("hello", date="2026-07-03")
        with patch("src.notifier.journal_sync.Client") as MockClient:
            journal_sync.sync_new_entry(entry_id, "hello", "", "")
            MockClient.assert_not_called()
        assert journal_store.get_notion_meta(entry_id) == ""

    def test_creates_page_and_saves_page_id(self, journal_dir, mock_notion):
        entry_id = journal_store.append_entry("hello world", date="2026-07-03")
        journal_sync.sync_new_entry(entry_id, "hello world", "key", "db-id")

        mock_notion.pages.create.assert_called_once()
        assert journal_store.get_notion_meta(entry_id) == "page-1"
        assert journal_store.get_notion_url(entry_id) == "https://notion.so/page-1"

    def test_page_creation_failure_does_not_raise(self, journal_dir, mock_notion):
        mock_notion.pages.create.side_effect = Exception("boom")
        entry_id = journal_store.append_entry("hello", date="2026-07-03")
        journal_sync.sync_new_entry(entry_id, "hello", "key", "db-id")
        assert journal_store.get_notion_meta(entry_id) == ""

    def test_item_label_preserved_alongside_notion_meta(self, journal_dir, mock_notion):
        entry_id = journal_store.append_entry("hello", date="2026-07-03")
        journal_store.save_item(entry_id, "label")
        journal_sync.sync_new_entry(entry_id, "hello", "key", "db-id")

        assert journal_store.get_item(entry_id) == "label"
        assert journal_store.get_notion_meta(entry_id) == "page-1"


class TestSyncAppend:
    def test_no_credentials_no_op(self, journal_dir):
        entry_id = journal_store.append_entry("hello", date="2026-07-03")
        with patch("src.notifier.journal_sync.Client") as MockClient:
            journal_sync.sync_append(entry_id, "more", "", "")
            MockClient.assert_not_called()

    def test_appends_blocks_to_existing_page(self, journal_dir, mock_notion):
        entry_id = journal_store.append_entry("hello", date="2026-07-03")
        journal_store.save_notion_meta(entry_id, "existing-page")

        journal_sync.sync_append(entry_id, "more content", "key", "db-id")

        mock_notion.blocks.children.append.assert_called_once()
        _, kwargs = mock_notion.blocks.children.append.call_args
        assert kwargs["block_id"] == "existing-page"
        mock_notion.pages.create.assert_not_called()

    def test_falls_back_to_create_when_no_page_id(self, journal_dir, mock_notion):
        entry_id = journal_store.append_entry("hello", date="2026-07-03")

        journal_sync.sync_append(entry_id, "more content", "key", "db-id")

        mock_notion.pages.create.assert_called_once()
        assert journal_store.get_notion_meta(entry_id) == "page-1"
