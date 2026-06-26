"""Handler that creates the weekly briefing recap page in Notion."""
from datetime import date

from src.config import CONFIG
from src.constants import BRIEFING_OUTPUT_DIR
from src.generator.weekly_summary import generate_weekly_summary, week_label
from src.notifier.local_md import write_md_file
from src.notifier.notion import fetch_weekly_pages, send_to_notion
from src.logger import get_logger

logger = get_logger(__name__)


def weekly_handler(event=None, context=None):
    """Aggregate the last 7 days of briefings and create a weekly recap page in Notion."""
    logger.info("=== weekly recap start ===")

    logger.info("fetching the last 7 days of pages from Notion...")
    pages = fetch_weekly_pages(
        CONFIG.notion_api_key,
        CONFIG.notion_database_id,
        days=7,
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
    logger.info("=== done ===")
    return {"statusCode": 200, "body": f"Weekly summary posted: {page_url}"}


if __name__ == "__main__":
    weekly_handler()
