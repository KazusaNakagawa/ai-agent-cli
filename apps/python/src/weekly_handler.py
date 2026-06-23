"""Handler that creates the weekly briefing recap page in Notion."""
from src.config import CONFIG
from src.generator.weekly_summary import generate_weekly_summary, week_label
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
