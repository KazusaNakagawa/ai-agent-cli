"""Reusable chat-session command builder for daily briefing Q&A.

Used by both ``bin/chat.py`` (interactive CLI launcher) and
``web/routers/chat.py`` (SSE endpoint). The function is intentionally
silent — print/log output stays in the callers so SSE consumers don't
receive informational text in the response stream.
"""
import uuid
from pathlib import Path


def session_name_for(target_date: str) -> str:
    return f"briefing-chat-{target_date}"


def build_cmd(target_date: str, briefing_file: Path, session_file: Path) -> list[str]:
    """Return claude CLI args, resuming if a saved session exists, else creating
    a new one and persisting the UUID to ``session_file``.

    - Resume: ``claude --resume <uuid> --name <name>``
    - New:    ``claude --session-id <uuid> --name <name> --append-system-prompt <briefing>``
    """
    name = session_name_for(target_date)

    if session_file.exists():
        session_id = session_file.read_text().strip()
        return ["claude", "--resume", session_id, "--name", name]

    session_id = str(uuid.uuid4())
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(session_id)

    briefing_content = briefing_file.read_text()
    context = (
        f"以下は {target_date} のマーケットブリーフィングです。"
        "このブリーフィングをコンテキストとして、ユーザーの質問に日本語で回答してください。\n\n"
        f"=== マーケットブリーフィング ({target_date}) ===\n"
        f"{briefing_content}\n"
        "=== END ==="
    )
    return [
        "claude",
        "--session-id", session_id,
        "--name", name,
        "--append-system-prompt", context,
    ]
