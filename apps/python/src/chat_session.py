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


def build_cmd(
    target_date: str,
    briefing_file: Path,
    session_file: Path,
    history_context: str | None = None,
) -> list[str]:
    """Return claude CLI args, resuming if a saved session exists, else creating
    a new one and persisting the UUID to ``session_file``.

    - Resume: ``claude --resume <uuid> --name <name>``
    - New:    ``claude --session-id <uuid> --name <name> --append-system-prompt <briefing>``

    ``history_context`` (#395) is retrieved cross-date excerpts from past
    briefings, injected alongside today's briefing only when a new session is
    created — a resumed session already has its context baked in, so it is
    ignored on resume.
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
    if history_context:
        context += (
            "\n\n以下は過去ブリーフィングから検索された関連抜粋です。"
            "質問が過去の日付に関する場合の参考にしてください。"
            "各抜粋は冒頭に `[ファイル名:行範囲]` の形式で出典を示しています。"
            "回答内でこれらの抜粋の内容に触れる際は、"
            "対応するファイル名（例: briefing_2026-05-01.md）を括弧書きで明記し、"
            "どの日付の情報かを読み手が追跡できるようにしてください。\n\n"
            "=== 過去ブリーフィングの関連抜粋 ===\n"
            f"{wrap_untrusted(history_context, label='historical_briefing_excerpts')}\n"
            "=== END ==="
        )
    return [
        "claude",
        "--session-id", session_id,
        "--name", name,
        "--append-system-prompt", context,
    ]
