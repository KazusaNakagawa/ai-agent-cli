import re
from pathlib import Path

# Claude model
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Claude CLI timeouts (seconds)
TIMEOUT_BRIEFING_MAIN = 300
TIMEOUT_BRIEFING_SECTORS = 480
TIMEOUT_WEEKLY_SUMMARY = 300

# Log retention
LOG_RETENTION_DAYS = 7

# Output directory for MD fallback
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Notion
NOTION_CHAR_LIMIT = 2000
NOTION_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\)]+)\)")
NOTION_LABEL_COLON_RE = re.compile(r"^([-*]\s+)?([^：\n]{1,30}：)(.+)")
NOTION_LIST_TYPES = {"numbered_list_item", "bulleted_list_item"}
NOTION_INDENT_RE = re.compile(r"^( {2,}|\t)([-*]|\d+\.)\s+(.*)")
NOTION_HEADING_RE = re.compile(r"^#{1,}\s")
