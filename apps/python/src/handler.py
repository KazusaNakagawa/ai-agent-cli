from datetime import date

from src.claude_runner import get_model
from src.config import CONFIG
from src.constants import BRIEFING_MD_RETENTION_DAYS, BRIEFING_MD_ROTATION_ENABLED, BRIEFING_OUTPUT_DIR, BRIEFING_SKIP_IF_EXISTS
from src.fetcher.stocks import fetch_stock_moves
from src.generator.briefing import generate_briefing
from src.metrics.briefing import extract_briefing_metrics
from src.notifier.discord import send_to_discord
from src.notifier.local_md import save_briefing_md
from src.notifier.notion import send_to_notion
from src.logger import get_logger
from src.utils import is_configured as _is_configured

logger = get_logger(__name__)


def _preflight() -> None:
    """Log a WARNING for each missing credential before the pipeline starts."""
    if not _is_configured(CONFIG.discord_token, CONFIG.discord_channel_id):
        logger.warning("DISCORD_TOKEN or CHANNEL_ID unset — skipping Discord notification")
    if not _is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id):
        logger.warning("NOTION_API_KEY or NOTION_DATABASE_ID unset — skipping Notion notification")


def lambda_handler(event=None, context=None, *, dry_run: bool = False, force: bool = False):
    """Lambda handler that generates the stock briefing and delivers it to Discord/Notion/local MD."""
    logger.info("=== My World Briefing start ===")
    _preflight()

    if dry_run:
        logger.info("Dry-run mode — skipping the pipeline")
        return {"statusCode": 200, "body": "dry-run"}

    if BRIEFING_SKIP_IF_EXISTS and not force:
        today_md = BRIEFING_OUTPUT_DIR / f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
        if today_md.exists():
            logger.info(
                "Briefing already generated today (%s) — skipping. Pass --force to override.",
                today_md,
            )
            return {"statusCode": 200, "body": "skipped (already generated today)"}

    logger.info("fetching stock moves...")
    stocks = fetch_stock_moves(CONFIG.portfolio.tickers)

    logger.info("generating briefing (WebSearch)...")
    briefing = generate_briefing(stocks, CONFIG)

    logger.debug("briefing generated (length=%d)", len(briefing))

    discord_ok = _is_configured(CONFIG.discord_token, CONFIG.discord_channel_id)
    notion_ok = _is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id)

    # Write local MD first: keep the body on disk even if Discord/Notion raise.
    md_written = False
    try:
        save_briefing_md(
            briefing,
            BRIEFING_OUTPUT_DIR,
            BRIEFING_MD_RETENTION_DAYS,
            rotation_enabled=BRIEFING_MD_ROTATION_ENABLED,
        )
        md_written = True
    except OSError as exc:
        logger.warning("local MD write failed: %s — continuing", exc)

    if discord_ok:
        logger.info("sending to Discord...")
        send_to_discord(briefing, CONFIG.discord_token, CONFIG.discord_channel_id)

    if notion_ok:
        logger.info("creating Notion page...")
        model = get_model()
        notion_text = briefing + f"\n\n---\nModel: {model}"
        metrics = extract_briefing_metrics(briefing, CONFIG.portfolio.tickers)
        page_url = send_to_notion(
            notion_text,
            CONFIG.notion_api_key,
            CONFIG.notion_database_id,
            title=f"マーケットブリーフィング — {date.today().strftime('%Y-%m-%d')}",
            tags=["agent"],
            extra_properties=metrics,
        )
        if page_url:
            logger.info("Notion ページ: %s", page_url)

    logger.info("=== done ===")
    return {"statusCode": 200, "body": "Briefing sent.", "md_written": md_written}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="My World Briefing agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate credentials and config without running the pipeline")
    parser.add_argument("--force", action="store_true",
                        help="Run even if today's briefing MD already exists (overrides BRIEFING_SKIP_IF_EXISTS)")
    args = parser.parse_args()
    lambda_handler(dry_run=args.dry_run, force=args.force)
