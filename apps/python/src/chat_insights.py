"""Archive chat.sh conversations and analyze how they are used.

chat.sh only records a Claude session id per briefing date
(``output/briefing/.sessions/<date>``). The conversation itself lives in
Claude Code's transcript store, which prunes old transcripts (30 days by
default), so most of the history is gone before anyone looks at it. The
archive step copies each session's turns into ``output/chat_archive/`` while
the transcript still exists; the analysis step reads that archive back.

The archive never shrinks: a session whose transcript has already been pruned
keeps whatever was archived for it earlier.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from src import paths

SESSIONS_DIR = paths.OUTPUT_DIR / "briefing" / ".sessions"
ARCHIVE_DIR = paths.OUTPUT_DIR / "chat_archive"
REPORT_DIR = paths.OUTPUT_DIR / "chat_insights"
TRANSCRIPTS_DIR = Path.home() / ".claude" / "projects"

WINDOW_DAYS = 28
SHORT_PROMPT_CHARS = 20

# Text the harness injects as a "user" turn: system reminders, loaded skill
# bodies, tool-load acknowledgements, and the briefing context chat.sh sends
# as the first message of a new session.
_INJECTED_PREFIXES = (
    "<",
    "Base directory for this skill",
    "Tool loaded",
    "[Request interrupted",
)


@dataclass
class ArchiveResult:
    archived: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def _is_injected(text: str) -> bool:
    if text.startswith(_INJECTED_PREFIXES):
        return True
    return text.startswith("以下は") and "ブリーフィング" in text[:60]


def _text_of(content) -> str | None:
    """Return the plain text of a message, or None for a tool-only message."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(texts) if texts else None


def _tool_names(content) -> list[str]:
    if not isinstance(content, list):
        return []
    names = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "tool_use":
            name = c.get("name", "")
            if name == "Skill":
                name = f"Skill:{c.get('input', {}).get('skill', '')}"
            elif name.startswith("mcp__"):
                # mcp__<server>__<tool> → <tool>; the server prefix is noise here.
                name = name.rsplit("__", 1)[-1]
            names.append(name)
    return names


def extract_turns(transcript: Path, session_date: str) -> list[dict]:
    """Read one Claude Code transcript and return its human-readable turns.

    User turns keep only what the person typed. Assistant turns keep their text
    and the names of the tools they called, which is enough to see what kind of
    work a request turned into without archiving tool payloads.
    """
    turns: list[dict] = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = ev.get("type")
        if role not in ("user", "assistant") or ev.get("isMeta"):
            continue
        content = ev.get("message", {}).get("content")
        text = (_text_of(content) or "").strip()
        tools = _tool_names(content) if role == "assistant" else []
        if role == "user" and (not text or _is_injected(text)):
            continue
        if role == "assistant" and not text and not tools:
            continue
        turns.append(
            {"date": session_date, "ts": ev.get("timestamp"), "role": role, "text": text, "tools": tools}
        )
    return turns


def _find_transcript(session_id: str, transcripts_dir: Path) -> Path | None:
    hits = sorted(transcripts_dir.glob(f"*/{session_id}.jsonl"))
    return hits[0] if hits else None


def archive_sessions(
    sessions_dir: Path = SESSIONS_DIR,
    transcripts_dir: Path = TRANSCRIPTS_DIR,
    archive_dir: Path = ARCHIVE_DIR,
) -> ArchiveResult:
    """Copy every chat.sh session whose transcript still exists into the archive."""
    result = ArchiveResult()
    if not sessions_dir.is_dir():
        return result
    archive_dir.mkdir(parents=True, exist_ok=True)
    for session_file in sorted(p for p in sessions_dir.iterdir() if p.is_file()):
        session_date = session_file.name
        transcript = _find_transcript(session_file.read_text().strip(), transcripts_dir)
        if transcript is None:
            result.missing.append(session_date)
            continue
        turns = extract_turns(transcript, session_date)
        if not turns:
            continue
        out = archive_dir / f"{session_date}.jsonl"
        out.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in turns) + "\n", encoding="utf-8")
        result.archived.append(session_date)
    return result


def load_archive(archive_dir: Path, since: date) -> list[dict]:
    """Return archived turns from sessions dated on or after ``since``."""
    turns: list[dict] = []
    if not archive_dir.is_dir():
        return turns
    for f in sorted(archive_dir.glob("*.jsonl")):
        try:
            if date.fromisoformat(f.stem) < since:
                continue
        except ValueError:
            continue
        turns.extend(json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
    return turns


def _local_hour(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().hour
    except ValueError:
        return None


def compute_stats(turns: Iterable[dict]) -> dict:
    """Deterministic usage numbers, computed here so the model never has to count."""
    turns = list(turns)
    user = [t for t in turns if t["role"] == "user"]
    lengths = [len(t["text"]) for t in user]
    hours = Counter(h for h in (_local_hour(t["ts"]) for t in user) if h is not None)
    tools = Counter(name for t in turns for name in t.get("tools", []))
    skills = Counter(n.split(":", 1)[1] for n in tools.elements() if n.startswith("Skill:"))
    return {
        "sessions": len({t["date"] for t in turns}),
        "user_turns": len(user),
        "median_prompt_chars": statistics.median(lengths) if lengths else 0,
        "short_prompts": sum(n <= SHORT_PROMPT_CHARS for n in lengths),
        "hours": dict(sorted(hours.items())),
        "top_tools": dict(Counter({k: v for k, v in tools.items() if not k.startswith("Skill:")}).most_common(10)),
        "skills": dict(skills.most_common()),
    }


def build_prompt(turns: list[dict], stats: dict, missing: list[str]) -> str:
    from src.generator.prompt import render
    from src.prompt_safety import wrap_untrusted

    user_lines = "\n".join(
        f"[{t['date']}] {t['text'].replace(chr(10), ' ')[:300]}" for t in turns if t["role"] == "user"
    )
    return render(
        "chat_insights",
        stats=json.dumps(stats, ensure_ascii=False, indent=2),
        missing=", ".join(missing) if missing else "なし",
        turns=wrap_untrusted(user_lines, label="chat_user_turns"),
    )


def window_start(today: date, days: int = WINDOW_DAYS) -> date:
    return today - timedelta(days=days)
