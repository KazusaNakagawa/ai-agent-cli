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


def send_to_discord(text: str, token: str, channel_id: str):
    """Discord Bot API でチャンネルにメッセージ送信（2000文字制限を考慮して分割）"""
    if not token or not channel_id:
        logger.error("DISCORD_TOKEN または CHANNEL_ID が未設定")
        return
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}"}
    text = _wrap_tables_in_codeblock(text)
    chunk_size = 1900
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    for i, chunk in enumerate(chunks, 1):
        res = requests.post(url, headers=headers, json={"content": chunk})
        res.raise_for_status()
        logger.debug("Discord 送信完了 (chunk %d/%d)", i, len(chunks))
    logger.info("Discord 送信完了 (合計%dチャンク)", len(chunks))
