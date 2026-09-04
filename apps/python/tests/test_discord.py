from unittest.mock import MagicMock, patch

import requests

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

    def test_language_fence_closed_at_chunk_boundary(self):
        # ```python のような言語指定フェンスがチャンク境界をまたぐとき
        # 各チャンクのフェンス数は偶数（= バランスが取れている）
        fence_text = "```python\n" + "x = 1\n" * 100 + "```\n"
        chunks = _chunk_preserving_fences(fence_text, chunk_size=500)
        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            count = chunk.count("```")
            assert count % 2 == 0, f"chunk {i + 1}: フェンス数が奇数 ({count})"

    def test_language_specifier_preserved_on_reopen(self):
        # チャンク分割後の継続チャンクが元の言語指定フェンスで再開される
        fence_text = "```python\n" + "x = 1\n" * 100 + "```\n"
        chunks = _chunk_preserving_fences(fence_text, chunk_size=500)
        assert len(chunks) > 1
        # 最初のチャンク以外（継続チャンク）は ```python で始まる
        for chunk in chunks[1:]:
            if chunk.startswith("```"):
                assert chunk.startswith("```python\n"), (
                    f"継続チャンクが言語指定なしで再開: {repr(chunk[:30])}"
                )

    def test_fence_state_correct_when_closing_fence_causes_overflow(self):
        # 閉じフェンス行自体がチャンク境界を超えるとき、前チャンクが正しく閉じられる
        # "```\n"(4) + 247 * "x\n"(2) = 498 chars → 閉じ"```\n"(4) で 502 > 500
        inner = "x\n" * 247  # 494 文字
        fence_text = "```\n" + inner + "```\n"
        chunks = _chunk_preserving_fences(fence_text, chunk_size=500)
        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            count = chunk.count("```")
            assert count % 2 == 0, f"chunk {i + 1}: フェンス数が奇数 ({count})"


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


class TestSendToDiscordAttachment:
    def _png(self, tmp_path):
        path = tmp_path / "price-comparison-20260905.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return path

    def test_attachment_posted_as_multipart_after_the_text(self, tmp_path):
        # 本文は従来どおり JSON、添付は後続メッセージとして multipart で送る
        png = self._png(tmp_path)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("src.notifier.discord.requests.post", return_value=mock_resp) as mock_post:
            send_to_discord("hello", token="tok", channel_id="ch123", attachment=png)

        assert mock_post.call_count == 2
        text_call, file_call = mock_post.call_args_list
        assert text_call.kwargs["json"]["content"] == "hello"
        assert "files" not in text_call.kwargs
        filename, data, mime = file_call.kwargs["files"]["files[0]"]
        assert filename == png.name
        assert data == png.read_bytes()
        assert mime == "image/png"

    def test_no_attachment_keeps_the_json_only_post(self, tmp_path):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("src.notifier.discord.requests.post", return_value=mock_resp) as mock_post:
            send_to_discord("hello", token="tok", channel_id="ch123")
        assert mock_post.call_count == 1
        assert "files" not in mock_post.call_args.kwargs

    def test_missing_attachment_file_is_skipped(self, tmp_path):
        # 生成に失敗してパスだけ残ったケース: 本文は送られ、例外は出さない
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("src.notifier.discord.requests.post", return_value=mock_resp) as mock_post:
            send_to_discord(
                "hello", token="tok", channel_id="ch123", attachment=tmp_path / "gone.png"
            )
        assert mock_post.call_count == 1

    def test_upload_failure_does_not_raise(self, tmp_path):
        """本文送信後に添付だけ失敗しても例外にしない。

        step_deliver_discord は best_effort ではないので、ここで送出すると
        既に配信済みのブリーフィングごと run が failed になる。
        """
        png = self._png(tmp_path)
        ok = MagicMock()
        ok.raise_for_status.return_value = None
        with patch(
            "src.notifier.discord.requests.post",
            side_effect=[ok, requests.RequestException("413 payload too large")],
        ) as mock_post:
            send_to_discord("hello", token="tok", channel_id="ch123", attachment=png)
        assert mock_post.call_count == 2
