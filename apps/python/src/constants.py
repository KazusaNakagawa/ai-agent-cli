import re
from pathlib import Path

# Claude model
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Claude CLI timeouts (seconds)
# One uniform budget for every run_claude() call. WebSearch-heavy prompts have a
# long tail: observed durations range 110-422s, and the previous 480s budget left
# only ~1.15x headroom over the worst case, so an outlier run discarded several
# minutes of billed work (2026-07-26 briefing). 900s covers the tail without
# adding retries, which would re-run the whole prompt from scratch.
TIMEOUT_CLAUDE_DEFAULT = 900
TIMEOUT_BRIEFING_MAIN = TIMEOUT_CLAUDE_DEFAULT
TIMEOUT_BRIEFING_SECTORS = TIMEOUT_CLAUDE_DEFAULT
TIMEOUT_WEEKLY_SUMMARY = TIMEOUT_CLAUDE_DEFAULT

# Claude CLI retry policy (5xx transient errors only)
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 5.0  # seconds; first retry waits this long
RETRY_BACKOFF_FACTOR = 3.0  # 5s -> 15s -> 45s

# Briefing calls (main analysis + sector sweep) get a tighter retry budget:
# each attempt re-runs the full WebSearch prompt from scratch (~$0.6-$0.9 per
# attempt observed), so the module default of 3 would triple worst-case token
# spend on a string of transient errors.
RETRY_MAX_ATTEMPTS_BRIEFING = 2

# Log retention
LOG_RETENTION_DAYS = 7

# Weekly recap lookback window (briefing pages + Notion comment ingestion, #396)
WEEKLY_WINDOW_DAYS = 7

# Output directory for MD output
OUTPUT_DIR = Path(__file__).parent.parent / "output"
BRIEFING_OUTPUT_DIR = OUTPUT_DIR / "briefing"
# Salvaged text from claude CLI calls that ultimately failed (see run_claude)
PARTIAL_OUTPUT_DIR = OUTPUT_DIR / "partial"

# Briefing local MD retention (number of newest dated files to keep)
BRIEFING_MD_RETENTION_DAYS = 7
# When False, _prune_old is skipped and all dated files are kept indefinitely
BRIEFING_MD_ROTATION_ENABLED = False
# When True, skip the pipeline if today's briefing MD already exists (prevents
# duplicate runs from LaunchAgent wake-from-sleep + manual invocation overlap).
# Set to False or pass --force on the CLI to re-run on the same day.
BRIEFING_SKIP_IF_EXISTS: bool = True

# Notion
NOTION_CHAR_LIMIT = 2000
NOTION_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\)]+)\)")
NOTION_LABEL_COLON_RE = re.compile(r"^([-*]\s+)?([^：\n]{1,30}：)(.+)")
NOTION_LIST_TYPES = {"numbered_list_item", "bulleted_list_item"}
NOTION_INDENT_RE = re.compile(r"^( {2,}|\t)([-*]|\d+\.)\s+(.*)")
NOTION_HEADING_RE = re.compile(r"^#{1,}\s")
