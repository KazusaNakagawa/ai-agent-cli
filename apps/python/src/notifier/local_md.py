import re
from datetime import date
from pathlib import Path

from src.generator.briefscript_schema import BriefingDocument
from src.logger import get_logger

logger = get_logger(__name__)

_BRIEFING_FILE_RE = re.compile(r"^briefing_(\d{4}-\d{2}-\d{2})\.md$")
_DOCUMENT_FILE_RE = re.compile(r"^briefing_(\d{4}-\d{2}-\d{2})\.json$")


def save_briefing_md(
    text: str,
    output_dir: Path,
    retention_days: int,
    today: date | None = None,
    *,
    rotation_enabled: bool = True,
) -> Path:
    """Write the briefing body as briefing_YYYY-MM-DD.md.

    When rotation_enabled=True, keep the newest retention_days files matching the
    same pattern in output_dir and delete the rest.
    When rotation_enabled=False, delete nothing and retain all files unbounded.
    """
    if retention_days < 1:
        raise ValueError(
            f"retention_days must be >= 1 (got {retention_days})"
        )

    today = today or date.today()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"briefing_{today.strftime('%Y-%m-%d')}.md"
    path.write_text(text, encoding="utf-8")
    logger.info("local MD written: %s (%d chars)", path, len(text))

    if rotation_enabled:
        _prune_old(output_dir, retention_days)
    else:
        logger.debug("rotation disabled — not deleting old MD files")
    return path


def save_briefing_document(
    doc: BriefingDocument,
    output_dir: Path,
    retention_days: int,
    *,
    rotation_enabled: bool = True,
) -> Path:
    """Write the briefing IR as briefing_YYYY-MM-DD.json, dated by the document.

    Rotated on the same terms as the MD, so the two stay paired.
    """
    if retention_days < 1:
        raise ValueError(
            f"retention_days must be >= 1 (got {retention_days})"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"briefing_{doc.date.strftime('%Y-%m-%d')}.json"
    path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    logger.info("briefing IR written: %s", path)

    if rotation_enabled:
        _prune_old(output_dir, retention_days, _DOCUMENT_FILE_RE)
    return path


def write_md_file(output_dir: Path, filename: str, text: str) -> Path:
    """Write text to output_dir/filename, creating the directory if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(text, encoding="utf-8")
    logger.info("MD written: %s (%d chars)", path, len(text))
    return path


def _prune_old(
    output_dir: Path, retention_days: int, pattern: re.Pattern[str] = _BRIEFING_FILE_RE,
) -> None:
    matched = [
        p for p in output_dir.iterdir()
        if p.is_file() and pattern.match(p.name)
    ]
    matched.sort(key=lambda p: p.name, reverse=True)  # ISO date sorts lexicographically
    for stale in matched[retention_days:]:
        try:
            stale.unlink()
            logger.info("deleted old MD: %s", stale.name)
        except FileNotFoundError:
            pass


def save_slides(deck: str, output_dir: Path, day: date) -> Path:
    """Write the Marp deck as ``briefing_YYYY-MM-DD.slides.md`` (#518)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"briefing_{day.strftime('%Y-%m-%d')}.slides.md"
    path.write_text(deck, encoding="utf-8")
    logger.info("slide deck written: %s", path)
    return path
