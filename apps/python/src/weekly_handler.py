"""Handler that creates the weekly briefing recap page in Notion."""
from datetime import date

from src import judgment_ingest, notion_comment_state
from src.config import CONFIG
from src.constants import BRIEFING_OUTPUT_DIR, WEEKLY_WINDOW_DAYS
from src.generator.weekly_summary import generate_weekly_summary, week_label
from src.notifier.local_md import write_md_file
from src.notifier.notion import (
    fetch_commentable_pages,
    fetch_new_comments,
    fetch_weekly_pages,
    send_to_notion,
)
from src.logger import get_logger

logger = get_logger(__name__)


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


def weekly_handler(event=None, context=None):
    """Aggregate the last 7 days of briefings and create a weekly recap page in Notion."""
    logger.info("=== weekly recap start ===")

    logger.info("fetching the last 7 days of pages from Notion...")
    pages = fetch_weekly_pages(
        CONFIG.notion_api_key,
        CONFIG.notion_database_id,
        days=WEEKLY_WINDOW_DAYS,
    )

    if not pages:
        logger.warning("no target pages found; exiting.")
        return {"statusCode": 204, "body": "No pages found."}

    logger.info("generating weekly summary (%d pages)...", len(pages))
    summary = generate_weekly_summary(pages)
    title = f"週次振り返り — {week_label()}"

    # Persist locally so the recap shows up in the Briefing viewer alongside
    # daily briefings. Type prefix "weekly-summary" matches the briefing API's
    # filename convention, so listing/search/tabs work with no API change.
    # Best-effort: a local write failure must not block the Notion post.
    try:
        local_path = write_md_file(
            BRIEFING_OUTPUT_DIR,
            f"weekly-summary_{date.today().strftime('%Y-%m-%d')}.md",
            summary,
        )
    except OSError:
        logger.exception("failed to persist local weekly MD")
    else:
        logger.info("local weekly MD: %s", local_path)

    logger.info("creating Notion page...")
    page_url = send_to_notion(
        summary,
        CONFIG.notion_api_key,
        CONFIG.notion_database_id,
        title=title,
        tags=["weekly-summary"],
    )

    if not page_url:
        logger.error("failed to create the page in Notion")
        return {"statusCode": 500, "body": "Failed to post weekly summary to Notion."}

    logger.info("Notion page: %s", page_url)

    try:
        _ingest_notion_comments()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Notion comment ingestion failed: %s — continuing", exc)
    logger.info("=== done ===")
    return {"statusCode": 200, "body": f"Weekly summary posted: {page_url}"}


if __name__ == "__main__":
    weekly_handler()
