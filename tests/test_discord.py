from unittest.mock import MagicMock, patch

from src.notifier.discord import (
    _chunk_preserving_fences,
    _wrap_tables_in_codeblock,
    send_to_discord,
)


class TestWrapTablesInCodeblock:
    def test_table_wrapped_in_codeblock(self):
        text = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = _wrap_tables_in_codeblock(text)
        assert result.startswith("```")
        assert "```" in result

    def test_non_table_unchanged(self):
        text = "通常テキスト\n次の行"
        result = _wrap_tables_in_codeblock(text)
        assert "```" not in result
        assert "通常テキスト" in result

    def test_mixed_content(self):
        text = "見出し\n| A | B |\n|---|---|\n| 1 | 2 |\n末尾"
        result = _wrap_tables_in_codeblock(text)
        assert "見出し" in result
        assert "末尾" in result
        assert "```" in result


class TestChunkPreservingFences:
    def test_short_text_single_chunk(self):
        chunks = _chunk_preserving_fences("hello world")
        assert len(chunks) == 1
        assert chunks[0] == "hello world"

    def test_long_text_split_into_chunks(self):
        # 分割は行単位なので改行を含む長いテキストを使う
        text = "x" * 100 + "\n"
        text = text * 30  # 合計 3030 文字
        chunks = _chunk_preserving_fences(text, chunk_size=500)
        assert len(chunks) > 1

    def test_empty_text_returns_one_empty_chunk(self):
        chunks = _chunk_preserving_fences("")
        assert chunks == [""]

    def test_fence_closed_at_chunk_boundary(self):
        # フェンス内テキストを強制分割したとき ``` で閉じ・再開する
        fence_text = "```\n" + "line\n" * 200 + "```\n"
        chunks = _chunk_preserving_fences(fence_text, chunk_size=500)
        assert len(chunks) > 1
        for chunk in chunks[:-1]:
            assert chunk.endswith("```\n")


class TestSendToDiscord:
    def test_missing_token_returns_early(self):
        # 例外が出ないことを確認
        send_to_discord("msg", token="", channel_id="123")

    def test_missing_channel_id_returns_early(self):
        send_to_discord("msg", token="tok", channel_id="")

    def test_posts_to_discord_api(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("src.notifier.discord.requests.post", return_value=mock_resp) as mock_post:
            send_to_discord("hello", token="tok", channel_id="ch123")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["content"] == "hello"

    def test_large_text_sends_multiple_chunks(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("src.notifier.discord.requests.post", return_value=mock_resp) as mock_post:
            send_to_discord("x\n" * 2000, token="tok", channel_id="ch123")
        assert mock_post.call_count > 1
