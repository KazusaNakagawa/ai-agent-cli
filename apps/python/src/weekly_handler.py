"""The weekly briefing recap.

The pipeline is declared as a workflow in
``src/workflow/definitions/weekly.py``; the steps it references live here, next
to the fetchers and notifiers they use — the same split the daily briefing uses
in ``src.handler``. ``weekly_handler`` remains the entry point and keeps its
original signature and response shape for ``python -m src.weekly_handler`` and
the existing tests.
"""
import re
from datetime import date
from pathlib import Path

from src import judgment_ingest, notion_comment_state
from src.config import CONFIG
from src.constants import BRIEFING_OUTPUT_DIR, WEEKLY_RECAP_WEEKDAY, WEEKLY_WINDOW_DAYS
from src.generator.weekly_summary import generate_weekly_summary, week_label
from src.notifier.local_md import write_md_file
from src.notifier.notion import (
    fetch_commentable_pages,
    fetch_new_comments,
    fetch_weekly_pages,
    send_to_notion,
)
from src.logger import get_logger
from src.utils import is_configured as _is_configured
from src.workflow.registry import get as get_workflow
from src.workflow.runner import run_workflow

logger = get_logger(__name__)

_RECAP_FILE_RE = re.compile(r"^weekly-summary_(\d{4}-\d{2}-\d{2})\.md$")

_WEEKDAY_NAMES = ("月", "火", "水", "木", "金", "土", "日")


def _ingest_notion_comments() -> None:
    """Convert new Notion comments on briefing pages into judgment-learning-
    loop events (#396). Callers must wrap this in try/except — a hiccup here
    must never fail the weekly recap itself (degraded mode, same philosophy
    as the local-LLM briefing-indexing hook in ``src.handler``).
    """
    if not judgment_ingest.judge_available():
        logger.info(
            "judge CLI not found at %s — skipping Notion comment ingestion",
            judgment_ingest.JUDGE_BIN,
        )
        return

    pages = fetch_commentable_pages(CONFIG.notion_api_key, CONFIG.notion_database_id, days=WEEKLY_WINDOW_DAYS)
    if not pages:
        return

    seen_ids = notion_comment_state.read_seen_ids()
    new_comments = fetch_new_comments(CONFIG.notion_api_key, pages, seen_ids=seen_ids)
    if not new_comments:
        return

    ingested_ids = set(seen_ids)
    for comment in new_comments:
        if judgment_ingest.record_comment_as_judgment(comment):
            ingested_ids.add(comment["comment_id"])

    if ingested_ids != seen_ids:
        notion_comment_state.write_seen_ids(ingested_ids)
    logger.info(
        "ingested %d new Notion comment(s) into the judgment loop",
        len(ingested_ids) - len(seen_ids),
    )


# --- workflow guard ---------------------------------------------------------


def _existing_recap_this_week(today: date, output_dir: Path) -> Path | None:
    """Return this ISO week's recap file, if one was already written.

    ISO week membership rather than "a file exists": last week's recap must not
    suppress this week's, and a recap forced earlier in the same week must.
    An unparsable filename is ignored — a stray file in the output directory is
    not a reason to lose the recap.
    """
    if not output_dir.is_dir():
        return None
    this_week = today.isocalendar()[:2]
    for path in sorted(output_dir.glob("weekly-summary_*.md")):
        match = _RECAP_FILE_RE.match(path.name)
        if not match:
            continue
        try:
            written = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if written.isocalendar()[:2] == this_week:
            return path
    return None


def recap_reason_to_skip(today: date, output_dir: Path) -> str | None:
    """Return why the recap should not run on ``today``, or ``None`` to run.

    This is the rule that used to be the ``date +%u = 5`` branch in
    ``bin/run.sh``. Keeping it here rather than in the shell is what lets the
    recap be reached from ``bin/workflow.sh`` like every other workflow, and
    makes running it every day harmless.
    """
    if today.isoweekday() != WEEKLY_RECAP_WEEKDAY:
        expected = _WEEKDAY_NAMES[WEEKLY_RECAP_WEEKDAY - 1]
        actual = _WEEKDAY_NAMES[today.isoweekday() - 1]
        return f"the weekly recap runs on {expected}曜; today is {actual}曜 (--force to run anyway)"

    existing = _existing_recap_this_week(today, output_dir)
    if existing:
        return f"this week was already recapped ({existing.name}) (--force to run anyway)"
    return None


def weekly_guard(ctx) -> str | None:
    return recap_reason_to_skip(date.today(), BRIEFING_OUTPUT_DIR)


# --- workflow steps ---------------------------------------------------------


def step_preflight(ctx) -> None:
    """Log a WARNING when the recap's only delivery target is unreachable."""
    if not _is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id):
        logger.warning("NOTION_API_KEY or NOTION_DATABASE_ID unset — the recap cannot be delivered")


def step_fetch(ctx) -> list[dict]:
    logger.info("fetching the last %d days of pages from Notion...", WEEKLY_WINDOW_DAYS)
    pages = fetch_weekly_pages(
        CONFIG.notion_api_key,
        CONFIG.notion_database_id,
        days=WEEKLY_WINDOW_DAYS,
    )
    if not pages:
        logger.warning("no target pages found; exiting.")
    return pages


def skip_without_pages(ctx) -> bool:
    return not ctx.results["fetch"]


def step_summarize(ctx) -> str:
    pages = ctx.results["fetch"]
    logger.info("generating weekly summary (%d pages)...", len(pages))
    return generate_weekly_summary(pages)


def step_persist(ctx) -> str | None:
    """Write the recap locally before delivering it.

    The local copy is what makes the recap show up in the Briefing viewer
    alongside daily briefings — the ``weekly-summary`` prefix matches the
    briefing API's filename convention, so listing/search/tabs work with no API
    change. Only ``OSError`` is absorbed: a local write failure must not block
    the Notion post, but a real defect must still surface.
    """
    try:
        local_path = write_md_file(
            BRIEFING_OUTPUT_DIR,
            f"weekly-summary_{date.today().strftime('%Y-%m-%d')}.md",
            ctx.results["summarize"],
        )
    except OSError:
        logger.exception("failed to persist local weekly MD")
        return None
    logger.info("local weekly MD: %s", local_path)
    return str(local_path)


def step_deliver_notion(ctx) -> str | None:
    logger.info("creating Notion page...")
    page_url = send_to_notion(
        ctx.results["summarize"],
        CONFIG.notion_api_key,
        CONFIG.notion_database_id,
        title=f"週次振り返り — {week_label()}",
        tags=["weekly-summary"],
    )
    if not page_url:
        logger.error("failed to create the page in Notion")
        return page_url
    logger.info("Notion page: %s", page_url)
    return page_url


def skip_ingest(ctx) -> bool:
    """Ingest comments only once the recap itself landed.

    Covers both ways there is nothing to follow up on: a week with no pages
    (``deliver_notion`` never ran, so it left no result) and a delivery that
    came back without a page URL.
    """
    return not ctx.results.get("deliver_notion")


def step_ingest_comments(ctx) -> None:
    """Degraded mode (#396): the tolerance lives in the step rather than in
    ``Step.best_effort`` so the warning keeps naming Notion comment ingestion
    instead of a bare step id."""
    try:
        _ingest_notion_comments()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Notion comment ingestion failed: %s — continuing", exc)


# --- entry point ------------------------------------------------------------


def weekly_handler(event=None, context=None):
    """Run the weekly recap workflow and return the legacy response shape.

    ``force=True``: the guard exists to answer "should the recap run today?"
    for a caller that runs the workflow unconditionally, and this entry point
    is the opposite — it is invoked when the decision has already been made
    (manual recovery, or ``workflow run weekly`` having consulted the guard).
    """
    logger.info("=== weekly recap start ===")

    record = run_workflow(get_workflow("weekly"), force=True)

    if not record.results.get("fetch"):
        return {"statusCode": 204, "body": "No pages found."}

    page_url = record.results.get("deliver_notion")
    if not page_url:
        return {"statusCode": 500, "body": "Failed to post weekly summary to Notion."}

    logger.info("=== done ===")
    return {"statusCode": 200, "body": f"Weekly summary posted: {page_url}"}


if __name__ == "__main__":
    weekly_handler()
