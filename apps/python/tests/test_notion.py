from unittest.mock import MagicMock, patch

import pytest

from src.notifier.notion import (
    append_to_briefing_page,
    find_briefing_page,
    send_to_notion,
    _block_to_text,
    _markdown_to_blocks,
)


def _make_notion_mock(title_prop="Name", page_url="https://notion.so/page-1"):
    """notion.Client のモックを返す共通ファクトリ。"""
    mock = MagicMock()
    mock.databases.retrieve.return_value = {
        "properties": {title_prop: {"type": "title"}}
    }
    mock.pages.create.return_value = {"id": "page-id", "url": page_url}
    return mock


@pytest.fixture
def mock_notion():
    with patch("src.notifier.notion.Client") as MockClient:
        notion = _make_notion_mock()
        MockClient.return_value = notion
        yield notion


class TestSendToNotionMissingCredentials:
    def test_empty_api_key_returns_empty(self):
        result = send_to_notion("text", api_key="", database_id="db-id")
        assert result == ""

    def test_empty_database_id_returns_empty(self):
        result = send_to_notion("text", api_key="key", database_id="")
        assert result == ""


class TestSendToNotionTags:
    def test_no_tags_omits_tags_property(self, mock_notion):
        send_to_notion("hello", api_key="key", database_id="db-id", tags=None)

        _, kwargs = mock_notion.pages.create.call_args
        assert "Tags" not in kwargs["properties"]

    def test_single_tag_sets_multi_select(self, mock_notion):
        send_to_notion("hello", api_key="key", database_id="db-id", tags=["agent"])

        _, kwargs = mock_notion.pages.create.call_args
        assert kwargs["properties"]["Tags"] == {
            "multi_select": [{"name": "agent"}]
        }

    def test_multiple_tags_all_included(self, mock_notion):
        send_to_notion("hello", api_key="key", database_id="db-id", tags=["agent", "xss"])

        _, kwargs = mock_notion.pages.create.call_args
        assert kwargs["properties"]["Tags"] == {
            "multi_select": [{"name": "agent"}, {"name": "xss"}]
        }

    def test_returns_page_url(self, mock_notion):
        url = send_to_notion("hello", api_key="key", database_id="db-id", tags=["agent"])
        assert url == "https://notion.so/page-1"


class TestSendToNotionExtraProperties:
    def test_extra_properties_merged(self, mock_notion):
        send_to_notion(
            "hello",
            api_key="key",
            database_id="db-id",
            extra_properties={"CharCount": {"number": 5}},
        )
        _, kwargs = mock_notion.pages.create.call_args
        assert kwargs["properties"]["CharCount"] == {"number": 5}

    def test_extra_properties_and_tags_both_set(self, mock_notion):
        send_to_notion(
            "hello",
            api_key="key",
            database_id="db-id",
            tags=["agent"],
            extra_properties={"HighCount": {"number": 3}},
        )
        _, kwargs = mock_notion.pages.create.call_args
        props = kwargs["properties"]
        assert props["Tags"] == {"multi_select": [{"name": "agent"}]}
        assert props["HighCount"] == {"number": 3}

    def test_none_extra_properties_no_effect(self, mock_notion):
        send_to_notion("hello", api_key="key", database_id="db-id", extra_properties=None)
        _, kwargs = mock_notion.pages.create.call_args
        assert "CharCount" not in kwargs["properties"]


class TestMarkdownToBlocksNesting:
    def test_indented_bullet_becomes_child_of_numbered(self):
        md = "1. 項目A\n  - サブ項目"
        blocks = _markdown_to_blocks(md)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "numbered_list_item"
        children = blocks[0]["numbered_list_item"].get("children", [])
        assert len(children) == 1
        assert children[0]["type"] == "bulleted_list_item"

    def test_indented_tab_bullet_becomes_child(self):
        md = "1. 項目A\n\t- サブ項目"
        blocks = _markdown_to_blocks(md)
        assert len(blocks) == 1
        children = blocks[0]["numbered_list_item"].get("children", [])
        assert len(children) == 1

    def test_multiple_children(self):
        md = "1. 項目\n  - 子1\n  - 子2"
        blocks = _markdown_to_blocks(md)
        assert len(blocks) == 1
        children = blocks[0]["numbered_list_item"].get("children", [])
        assert len(children) == 2

    def test_non_indented_bullet_is_sibling(self):
        md = "1. 項目\n- 別項目"
        blocks = _markdown_to_blocks(md)
        assert len(blocks) == 2
        assert blocks[1]["type"] == "bulleted_list_item"


class TestHeadingBlocks:
    def test_bold_markers_stripped_from_heading(self):
        """見出しの ** が除去されること。"""
        blocks = _markdown_to_blocks("### **テーマ3**")
        assert blocks[0]["type"] == "heading_3"
        text = blocks[0]["heading_3"]["rich_text"][0]["text"]["content"]
        assert "**" not in text
        assert "テーマ3" in text

    def test_heading_with_colon_not_split(self):
        """見出し行は _split_label_colon の対象外であること。"""
        blocks = _markdown_to_blocks("### テーマ3：詳細")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "heading_3"

    def test_trailing_asterisks_stripped(self):
        """末尾だけ ** が残るパターンも除去されること。"""
        blocks = _markdown_to_blocks("### テーマ3**")
        assert blocks[0]["type"] == "heading_3"
        text = blocks[0]["heading_3"]["rich_text"][0]["text"]["content"]
        assert "**" not in text


class TestLabelColonSplit:
    def test_colon_stripped_from_label(self):
        """ラベル部分から末尾の「：」が除去されること。"""
        md = "- **米中技術競争の進展：**強い動き"
        blocks = _markdown_to_blocks(md)
        # ラベルブロックの rich_text に「：」が含まれないこと
        label_block = blocks[0]
        texts = [rt["text"]["content"] for rt in label_block[label_block["type"]]["rich_text"]]
        assert "：" not in "".join(texts)

    def test_fullwidth_colon_stripped(self):
        md = "**AI競争：**内容あり"
        blocks = _markdown_to_blocks(md)
        label_block = blocks[0]
        texts = [rt["text"]["content"] for rt in label_block[label_block["type"]]["rich_text"]]
        assert "：" not in "".join(texts)


class TestBlockToTextTableRow:
    def test_table_row_renders_pipe_format(self):
        block = {
            "type": "table_row",
            "table_row": {"cells": [
                [{"text": {"content": "週初"}}],
                [{"text": {"content": "週末"}}],
            ]},
        }
        assert _block_to_text(block) == "| 週初 | 週末 |"


# ---------------------------------------------------------------------------
# find_briefing_page / append_to_briefing_page (Issue #87)
# ---------------------------------------------------------------------------

def _title_prop(title: str) -> dict:
    return {
        "type": "title",
        "title": [{"type": "text", "text": {"content": title}}],
    }


class TestFindBriefingPage:
    def _setup(self, search_pages):
        mock = MagicMock()
        mock.search.return_value = {"results": search_pages, "has_more": False}
        patcher = patch("src.notifier.notion.Client", return_value=mock)
        patcher.start()
        return mock, patcher

    def test_returns_none_when_credentials_missing(self):
        assert find_briefing_page("", "db", "2026-05-30") is None
        assert find_briefing_page("k", "", "2026-05-30") is None

    def test_returns_matching_page_in_database(self):
        target_db = "db-uuid"
        page = {
            "id": "p1",
            "url": "https://www.notion.so/p1",
            "parent": {"database_id": target_db},
            "properties": {"Name": _title_prop("マーケットブリーフィング — 2026-05-30")},
        }
        _, patcher = self._setup([page])
        try:
            result = find_briefing_page("k", target_db, "2026-05-30")
            assert result is not None
            assert result["id"] == "p1"
        finally:
            patcher.stop()

    def test_skips_pages_in_other_databases(self):
        target_db = "right-db"
        page = {
            "id": "p1",
            "url": "https://www.notion.so/p1",
            "parent": {"database_id": "wrong-db"},
            "properties": {"Name": _title_prop("マーケットブリーフィング — 2026-05-30")},
        }
        _, patcher = self._setup([page])
        try:
            assert find_briefing_page("k", target_db, "2026-05-30") is None
        finally:
            patcher.stop()

    def test_skips_pages_with_mismatched_title(self):
        target_db = "db-uuid"
        page = {
            "id": "p1",
            "url": "https://www.notion.so/p1",
            "parent": {"database_id": target_db},
            "properties": {"Name": _title_prop("週次サマリー — 2026-05-30")},
        }
        _, patcher = self._setup([page])
        try:
            assert find_briefing_page("k", target_db, "2026-05-30") is None
        finally:
            patcher.stop()

    def test_database_id_match_is_dash_insensitive(self):
        # Notion sometimes returns ids with dashes, sometimes without.
        page = {
            "id": "p1",
            "url": "https://www.notion.so/p1",
            "parent": {"database_id": "abc-123-def"},
            "properties": {"Name": _title_prop("マーケットブリーフィング — 2026-05-30")},
        }
        _, patcher = self._setup([page])
        try:
            assert find_briefing_page("k", "abc123def", "2026-05-30") is not None
        finally:
            patcher.stop()


class TestAppendToBriefingPage:
    def test_returns_empty_when_page_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "src.notifier.notion.find_briefing_page",
            lambda *a, **kw: None,
        )
        assert append_to_briefing_page("k", "db", "2026-05-30", "body") == ""

    def test_appends_blocks_and_returns_page_url(self, monkeypatch):
        page = {"id": "p1", "url": "https://www.notion.so/p1"}
        monkeypatch.setattr(
            "src.notifier.notion.find_briefing_page",
            lambda *a, **kw: page,
        )
        client = MagicMock()
        monkeypatch.setattr("src.notifier.notion.Client", lambda auth: client)

        url = append_to_briefing_page("k", "db", "2026-05-30", "## hi\n\nbody")
        assert url == "https://www.notion.so/p1"
        client.blocks.children.append.assert_called_once()
        kwargs = client.blocks.children.append.call_args.kwargs
        assert kwargs["block_id"] == "p1"
        # Body produced two blocks (h2 + paragraph) — both passed in one batch.
        assert len(kwargs["children"]) == 2

    def test_returns_empty_when_notion_api_raises(self, monkeypatch):
        page = {"id": "p1", "url": "https://www.notion.so/p1"}
        monkeypatch.setattr(
            "src.notifier.notion.find_briefing_page",
            lambda *a, **kw: page,
        )
        client = MagicMock()
        client.blocks.children.append.side_effect = RuntimeError("boom")
        monkeypatch.setattr("src.notifier.notion.Client", lambda auth: client)

        assert append_to_briefing_page("k", "db", "2026-05-30", "body") == ""

    def test_splits_into_100_block_batches(self, monkeypatch):
        page = {"id": "p1", "url": "https://www.notion.so/p1"}
        monkeypatch.setattr(
            "src.notifier.notion.find_briefing_page",
            lambda *a, **kw: page,
        )
        client = MagicMock()
        monkeypatch.setattr("src.notifier.notion.Client", lambda auth: client)

        # 250 bullet lines → 250 blocks → 3 append calls (100, 100, 50).
        body = "\n".join(f"- item {i}" for i in range(250))
        url = append_to_briefing_page("k", "db", "2026-05-30", body)
        assert url == "https://www.notion.so/p1"
        assert client.blocks.children.append.call_count == 3
        sizes = [
            len(call.kwargs["children"])
            for call in client.blocks.children.append.call_args_list
        ]
        assert sizes == [100, 100, 50]
