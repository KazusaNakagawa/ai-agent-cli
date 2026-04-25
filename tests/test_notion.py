from unittest.mock import MagicMock, patch

import pytest

from src.notifier.notion import send_to_notion, _markdown_to_blocks


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
