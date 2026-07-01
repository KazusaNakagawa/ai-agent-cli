"""Weekly self-agent job: judgment-log entries -> persona report/profile -> Notion.

Mirrors the fetcher -> generator -> notifier pattern used by src/handler.py.
"""
from __future__ import annotations

import pathlib
import time

from src.config import CONFIG
from src.fetcher.judgment_log import fetch_new_entries, write_watermark
from src.generator.self_profile import generate_self_profile_update
from src.logger import get_logger
from src.notifier.notion import send_to_notion
from src.utils import is_configured

logger = get_logger(__name__)

OUTPUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "output" / "self_agent"
PROFILE_PATH = pathlib.Path(__file__).resolve().parent.parent / "config" / "self_agent_profile.md"


def _load_profile(path: pathlib.Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _write_report(report: str, out_dir: pathlib.Path) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"self_agent_report_{time.time_ns()}.md"
    out.write_text(report, encoding="utf-8")
    return out


def _apply_profile_diff(diff: str, path: pathlib.Path) -> None:
    """Append a durable profile diff. No-op when the diff is empty."""
    if not diff.strip():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write("\n\n" + diff + "\n")


def run(
    profile_path: pathlib.Path = PROFILE_PATH,
    output_dir: pathlib.Path = OUTPUT_DIR,
) -> dict:
    """Run one self-agent cycle and return a status dict."""
    new_entries = fetch_new_entries()
    if not new_entries:
        logger.info("no new judgment-log entries — skipping this run")
        return {"status": "skipped", "reason": "no new entries"}

    existing_profile = _load_profile(profile_path)
    # generate_self_profile_update only returns None for an empty new_entries
    # list, which is already excluded by the guard above.
    report, diff = generate_self_profile_update(new_entries, existing_profile)

    # Write the local report first: keep it on disk even if Notion delivery raises.
    report_path = _write_report(report, output_dir)

    page_url = ""
    if is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id):
        try:
            page_url = send_to_notion(
                report,
                CONFIG.notion_api_key,
                CONFIG.notion_database_id,
                title="Self-Agent Weekly Report",
            )
        except Exception as exc:
            logger.warning(
                "Notion delivery failed: %s — local report preserved at %s", exc, report_path
            )
    else:
        logger.warning("NOTION_API_KEY or NOTION_DATABASE_ID unset — skipping Notion delivery")

    _apply_profile_diff(diff, profile_path)

    # Advance the watermark only after the report has been generated and
    # written locally, so a failure earlier in the pipeline leaves the
    # watermark untouched and the same entries get retried next run.
    write_watermark(new_entries[-1]["id"])

    return {"status": "ok", "report_path": str(report_path), "notion_url": page_url}


def main() -> int:
    result = run()
    logger.info("self-agent run result: %s", result)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
