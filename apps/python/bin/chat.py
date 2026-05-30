"""Interactive Q&A session using a daily briefing as context."""
import argparse
import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
BRIEFING_DIR = PROJECT_ROOT / "output" / "briefing"
SESSIONS_DIR = BRIEFING_DIR / ".sessions"


def claude_env() -> dict[str, str]:
    """Return the parent environment without Anthropic API credentials."""
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def list_sessions(sessions_dir: Path) -> None:
    files = sorted(f for f in sessions_dir.iterdir() if f.is_file()) if sessions_dir.exists() else []
    if not files:
        print("No saved sessions.")
        return
    print("Saved chat sessions:")
    for f in files:
        print(f"  {f.name}  {f.read_text().strip()}")


def build_cmd(target_date: str, briefing_file: Path, session_file: Path) -> list[str]:
    """Return claude CLI args. Writes session_file with a new UUID on first call."""
    session_name = f"briefing-chat-{target_date}"

    if session_file.exists():
        session_id = session_file.read_text().strip()
        print(f"Resuming session: {session_name} ({session_id})")
        print("(type your question, Ctrl+C or /exit to quit)\n")
        return ["claude", "--resume", session_id, "--name", session_name]

    session_id = str(uuid.uuid4())
    session_file.write_text(session_id)

    briefing_content = briefing_file.read_text()
    context = (
        f"以下は {target_date} のマーケットブリーフィングです。"
        "このブリーフィングをコンテキストとして、ユーザーの質問に日本語で回答してください。\n\n"
        f"=== マーケットブリーフィング ({target_date}) ===\n"
        f"{briefing_content}\n"
        "=== END ==="
    )
    print(f"New session: {session_name} ({session_id})")
    print("(type your question, Ctrl+C or /exit to quit)\n")
    return [
        "claude",
        "--session-id", session_id,
        "--name", session_name,
        "--append-system-prompt", context,
    ]


def run_claude(target_date: str, briefing_file: Path, session_file: Path) -> int:
    """Run claude CLI and recreate the session if the saved id is stale.

    target_date selects the briefing/session label, briefing_file provides the
    initial context for new sessions, and session_file stores the saved Claude
    session id. Returns the final subprocess exit code.
    """
    env = claude_env()
    cmd = build_cmd(target_date, briefing_file, session_file)
    if "--resume" not in cmd:
        return subprocess.run(cmd, env=env).returncode

    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, env=env)
    stderr = result.stderr or ""

    if result.returncode == 0:
        return 0

    if "No conversation found" in stderr:
        print(stderr.strip(), file=sys.stderr)
        print("Saved session is stale; starting a new session.", file=sys.stderr)
        session_file.unlink(missing_ok=True)
        new_cmd = build_cmd(target_date, briefing_file, session_file)
        return subprocess.run(new_cmd, env=env).returncode

    if stderr:
        print(stderr.strip(), file=sys.stderr)
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat about a daily briefing")
    parser.add_argument(
        "date",
        nargs="?",
        default=date.today().strftime("%Y-%m-%d"),
        help="Briefing date (YYYY-MM-DD), default: today",
    )
    parser.add_argument("--list", action="store_true", help="List all saved sessions")
    args = parser.parse_args()

    if args.list:
        list_sessions(SESSIONS_DIR)
        return

    target_date = args.date
    briefing_file = BRIEFING_DIR / f"briefing_{target_date}.md"
    session_file = SESSIONS_DIR / target_date

    if not briefing_file.exists():
        print(f"Error: briefing file not found: {briefing_file}", file=sys.stderr)
        print("Usage: chat.sh [YYYY-MM-DD|--list]", file=sys.stderr)
        sys.exit(1)

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sys.exit(run_claude(target_date, briefing_file, session_file))


if __name__ == "__main__":
    main()
