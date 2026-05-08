import re
import requests
from src.logger import get_logger

logger = get_logger(__name__)


def _wrap_tables_in_codeblock(text: str) -> str:
    """Markdown テーブルブロックをコードブロックで囲み、Discord で等幅表示にする。"""
    lines = text.splitlines(keepends=True)
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        is_table = stripped.startswith("|") and stripped.endswith("|")
        is_sep = bool(re.fullmatch(r"[\|\s\-:]+", stripped) and "|" in stripped)
        if is_table or is_sep:
            table_lines = []
            while i < len(lines):
                s = lines[i].rstrip()
                if (s.startswith("|") and s.endswith("|")) or (re.fullmatch(r"[\|\s\-:]+", s) and "|" in s):
                    table_lines.append(lines[i].rstrip("\n"))
                    i += 1
                else:
                    break
            result.append("```\n" + "\n".join(table_lines) + "\n```\n")
            continue
        result.append(line)
        i += 1
    return "".join(result)


def _chunk_preserving_fences(text: str, chunk_size: int = 1900) -> list[str]:
    """テキストを chunk_size 以内に分割する。コードフェンス（```）をまたぐ場合は
    チャンク末尾でフェンスを閉じ、次チャンク先頭で再開することでバランスを保つ。"""
    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0
    in_fence = False

    for line in text.splitlines(keepends=True):
        # フェンス状態の更新より先に overflow を判定する（閉じフェンス行自体が
        # 境界を超えるケースで、まだ開いている状態のまま flush できるように）
        if current_len + len(line) > chunk_size and current_lines:
            chunk = "".join(current_lines)
            if in_fence:
                chunk += "```\n"   # 開いているフェンスを閉じる
            chunks.append(chunk)
            current_lines = []
            current_len = 0
            if in_fence:
                current_lines = ["```\n"]  # 次チャンクでフェンスを再開
                current_len = 4

        # 言語指定（```python 等）も含めてフェンス開閉を追跡する
        stripped = line.rstrip()
        if in_fence:
            if stripped == "```":
                in_fence = False
        elif stripped.startswith("```"):
            in_fence = True

        current_lines.append(line)
        current_len += len(line)

    if current_lines:
        chunks.append("".join(current_lines))
    return chunks or [""]


def send_to_discord(text: str, token: str, channel_id: str):
    """Discord Bot API でチャンネルにメッセージ送信（2000文字制限を考慮して分割）"""
    if not token or not channel_id:
        logger.error("DISCORD_TOKEN または CHANNEL_ID が未設定")
        return
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}"}
    text = _wrap_tables_in_codeblock(text)
    chunks = _chunk_preserving_fences(text)
    for i, chunk in enumerate(chunks, 1):
        res = requests.post(url, headers=headers, json={"content": chunk})
        res.raise_for_status()
        logger.debug("Discord 送信完了 (chunk %d/%d)", i, len(chunks))
    logger.info("Discord 送信完了 (合計%dチャンク)", len(chunks))
