import re
from pathlib import Path

# Claude model
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Claude CLI timeouts (seconds)
TIMEOUT_BRIEFING_MAIN = 300
TIMEOUT_BRIEFING_SECTORS = 480
TIMEOUT_WEEKLY_SUMMARY = 300

# Claude CLI retry policy (5xx transient errors only)
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 5.0  # seconds; first retry waits this long
RETRY_BACKOFF_FACTOR = 3.0  # 5s -> 15s -> 45s

# Log retention
LOG_RETENTION_DAYS = 7

# Output directory for MD output
OUTPUT_DIR = Path(__file__).parent.parent / "output"
BRIEFING_OUTPUT_DIR = OUTPUT_DIR / "briefing"

# Briefing local MD retention (number of newest dated files to keep)
BRIEFING_MD_RETENTION_DAYS = 7
# When False, _prune_old is skipped and all dated files are kept indefinitely
BRIEFING_MD_ROTATION_ENABLED = False

# Notion
NOTION_CHAR_LIMIT = 2000
NOTION_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\)]+)\)")
NOTION_LABEL_COLON_RE = re.compile(r"^([-*]\s+)?([^：\n]{1,30}：)(.+)")
NOTION_LIST_TYPES = {"numbered_list_item", "bulleted_list_item"}
NOTION_INDENT_RE = re.compile(r"^( {2,}|\t)([-*]|\d+\.)\s+(.*)")
NOTION_HEADING_RE = re.compile(r"^#{1,}\s")
