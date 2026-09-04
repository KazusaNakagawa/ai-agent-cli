import mimetypes
import re
from pathlib import Path

import requests

from src.logger import get_logger

logger = get_logger(__name__)


def _wrap_tables_in_codeblock(text: str) -> str:
    """Wrap Markdown table blocks in a code block so Discord renders them monospaced."""
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
    """Split text into chunks <= chunk_size. When a chunk would split across a code
    fence (```), close the fence at the chunk end and reopen it at the next chunk
    start to keep them balanced."""
    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0
    in_fence = False
    fence_opener = "```"

    for line in text.splitlines(keepends=True):
        # Check overflow before updating fence state (so that when a closing-fence
        # line itself crosses the boundary, we can flush while still "open").
        if current_len + len(line) > chunk_size and current_lines:
            chunk = "".join(current_lines)
            if in_fence:
                chunk += "```\n"   # close the open fence
            chunks.append(chunk)
            current_lines = []
            current_len = 0
            if in_fence:
                reopen = fence_opener + "\n"
                current_lines = [reopen]  # reopen the fence, preserving its language tag
                current_len = len(reopen)

        # Track fence open/close including the language tag (e.g. ```python)
        stripped = line.rstrip()
        if in_fence:
            if stripped == "```":
                in_fence = False
                fence_opener = "```"
        elif stripped.startswith("```"):
            in_fence = True
            fence_opener = stripped

        current_lines.append(line)
        current_len += len(line)

    if current_lines:
        chunks.append("".join(current_lines))
    return chunks or [""]


def _post_attachment(url: str, headers: dict, path: Path) -> None:
    """Upload one file as a follow-up message (multipart/form-data).

    Deliberately its own message rather than an attachment on the last text
    chunk: a multipart post that fails would otherwise take that chunk of the
    briefing down with it. For the same reason every failure here is absorbed —
    by the time this runs the text has already been delivered, and losing the
    chart is not worth failing a delivered briefing over.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        logger.warning("Discord attachment %s unreadable: %s — text already sent", path, exc)
        return
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        res = requests.post(
            url, headers=headers, files={"files[0]": (path.name, data, mime)}
        )
        res.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Discord attachment upload failed: %s — text already sent", exc)
        return
    logger.info("Discord attachment sent (%s, %d bytes)", path.name, len(data))


def send_to_discord(
    text: str,
    token: str,
    channel_id: str,
    attachment: str | Path | None = None,
):
    """Send a message to a channel via the Discord Bot API (chunked for the 2000-char limit).

    ``attachment`` is an optional local file posted as a follow-up message once
    the text is delivered; a missing path is skipped rather than raising.
    """
    if not token or not channel_id:
        logger.error("DISCORD_TOKEN or CHANNEL_ID unset")
        return
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}"}
    text = _wrap_tables_in_codeblock(text)
    chunks = _chunk_preserving_fences(text)
    for i, chunk in enumerate(chunks, 1):
        res = requests.post(url, headers=headers, json={"content": chunk})
        res.raise_for_status()
        logger.debug("Discord send done (chunk %d/%d)", i, len(chunks))
    logger.info("Discord send done (%d chunks total)", len(chunks))

    if attachment is None:
        return
    path = Path(attachment)
    if not path.is_file():
        logger.warning("Discord attachment %s does not exist — skipping", path)
        return
    _post_attachment(url, headers, path)
