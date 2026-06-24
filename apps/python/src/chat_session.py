"""Reusable chat-session command builder for daily briefing Q&A.

Used by both ``bin/chat.py`` (interactive CLI launcher) and
``web/routers/chat.py`` (SSE endpoint). The function is intentionally
silent — print/log output stays in the callers so SSE consumers don't
receive informational text in the response stream.
"""
import uuid
from pathlib import Path

from src.prompt_safety import wrap_untrusted


def session_name_for(target_date: str) -> str:
    return f"briefing-chat-{target_date}"


def journal_session_name_for(target_date: str) -> str:
    return f"journal-chat-{target_date}"


def build_journal_cmd(
    target_date: str, journal_context: str, session_file: Path
) -> list[str]:
    """Return claude CLI args for a journaling brainstorm session.

    Mirrors ``build_cmd`` but seeds the system prompt with the user's recent
    journal entries instead of a market briefing, so the assistant can help
    brainstorm and reflect over accumulated daily notes.

    - Resume: ``claude --resume <uuid> --name <name>``
    - New:    ``claude --session-id <uuid> --name <name> --append-system-prompt <context>``
    """
    name = journal_session_name_for(target_date)

    if session_file.exists():
        session_id = session_file.read_text().strip()
        return ["claude", "--resume", session_id, "--name", name]

    session_id = str(uuid.uuid4())
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(session_id)

    context = (
        "以下はユーザーの直近の日記（ジャーナル）です。"
        "これをコンテキストとして、アイディア出し・思考の整理・次の一手の検討など、"
        "ユーザーのブレインストーミングを日本語でサポートしてください。\n\n"
        f"=== ジャーナル ===\n"
        f"{wrap_untrusted(journal_context, label='journal_entries')}\n"
        "=== END ==="
    )
    return [
        "claude",
        "--session-id", session_id,
        "--name", name,
        "--append-system-prompt", context,
    ]


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
        f"{wrap_untrusted(briefing_content, label='previous_briefing')}\n"
        "=== END ==="
    )
    return [
        "claude",
        "--session-id", session_id,
        "--name", name,
        "--append-system-prompt", context,
    ]
