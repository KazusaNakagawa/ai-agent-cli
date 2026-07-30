"""Wake-up recovery for a sector sweep that a DarkWake sleep cut short.

The 05:00 launchd briefing usually fires during a DarkWake: macOS gives the job
roughly 45 seconds before going back to sleep, which severs the claude CLI's
HTTPS connection ("API Error: Connection closed mid-response"). The sector sweep
is the long half of the pipeline (~20 web searches), so it is the one that
reliably loses the race — measured on 2026-07-30 and 07-31.

This job re-runs *only* the sector sweep once the Mac is genuinely awake, splices
it into today's briefing MD, and appends it to the same Notion page. The main
analysis is never re-run, so a recovery costs about half of a full re-briefing.
"""

from datetime import date

from src.config import CONFIG
from src.constants import BRIEFING_MD_RETENTION_DAYS, BRIEFING_MD_ROTATION_ENABLED, BRIEFING_OUTPUT_DIR
from src.fetcher.fx import fetch_fx_context
from src.fetcher.stocks import fetch_stock_moves
from src.generator.briefing import SECTORS_FAILED_NOTICE, generate_sectors, merge_recovered_sectors
from src.logger import get_logger
from src.notifier.local_md import save_briefing_md
from src.notifier.notion import append_to_page_by_title
from src.power import is_system_awake
from src.utils import is_configured as _is_configured

logger = get_logger(__name__)

# A real sweep runs to several thousand characters. Anything this short is a
# stub or a stray status line, and splicing it in would destroy the briefing
# body it is supposed to complete (same rationale as looks_like_briefing).
_MIN_SECTORS_LENGTH = 200


def _result(body: str, status: int = 200) -> dict:
    return {"statusCode": status, "body": body}


def recover_sectors(event=None, context=None) -> dict:
    """Re-run today's sector sweep if it failed and the Mac is awake enough to finish it."""
    logger.info("=== sector sweep recovery start ===")

    today = date.today().strftime("%Y-%m-%d")
    md_path = BRIEFING_OUTPUT_DIR / f"briefing_{today}.md"
    if not md_path.exists():
        logger.info("no briefing MD for %s — nothing to recover", today)
        return _result("skipped (no briefing today)")

    body = md_path.read_text(encoding="utf-8")
    if SECTORS_FAILED_NOTICE not in body:
        logger.info("today's briefing already carries its sector sweep — nothing to recover")
        return _result("skipped (sectors already present)")

    if not is_system_awake():
        # Running now would just buy another severed connection.
        logger.info("system is in DarkWake or asleep — deferring recovery to the next run")
        return _result("skipped (system not fully awake)")

    # Re-fetch prices so the recovered sweep reasons about the same inputs the
    # sweep would have seen, rather than stale numbers parsed back out of the MD.
    fx, fx_change_pct = fetch_fx_context(CONFIG)
    stocks = fetch_stock_moves(CONFIG.portfolio.tickers, fx_change_pct)

    logger.info("re-running the sector sweep...")
    sectors = generate_sectors(stocks, CONFIG)

    if len(sectors.strip()) < _MIN_SECTORS_LENGTH:
        logger.warning(
            "recovered sweep is implausibly short (%d chars) — leaving today's MD untouched",
            len(sectors.strip()),
        )
        return _result("skipped (recovered sweep looks empty)")

    save_briefing_md(
        merge_recovered_sectors(body, sectors),
        BRIEFING_OUTPUT_DIR,
        BRIEFING_MD_RETENTION_DAYS,
        rotation_enabled=BRIEFING_MD_ROTATION_ENABLED,
    )

    if _is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id):
        page_url = append_to_page_by_title(
            "## セクター動向（リカバリ実行）\n\n" + sectors,
            CONFIG.notion_api_key,
            CONFIG.notion_database_id,
            title=f"マーケットブリーフィング — {today}",
        )
        if page_url:
            logger.info("Notion ページ: %s", page_url)
    else:
        logger.warning("NOTION_API_KEY or NOTION_DATABASE_ID unset — skipping Notion append")

    logger.info("=== sector sweep recovery done ===")
    return _result("sectors recovered")


if __name__ == "__main__":
    recover_sectors()
