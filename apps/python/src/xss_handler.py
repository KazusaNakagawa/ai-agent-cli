from datetime import date
from pathlib import Path

from src.config import get_xss_config
from src.constants import OUTPUT_DIR
from src.generator.xss_report import generate_xss_report
from src.metrics.xss import extract_xss_metrics
from src.notifier.discord import send_to_discord
from src.notifier.notion import send_to_notion
from src.logger import get_logger
from src.utils import is_configured as _is_configured

logger = get_logger(__name__)


def _write_md_fallback(text: str, filename: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename
    path.write_text(text, encoding="utf-8")
    return path


def _preflight(config) -> None:
    """Log a WARNING for each missing credential before the pipeline starts."""
    if not _is_configured(config.discord_token, config.discord_channel_id):
        logger.warning("DISCORD_TOKEN or CHANNEL_ID unset — skipping Discord notification")
    if not _is_configured(config.notion_api_key, config.notion_database_id):
        logger.warning("NOTION_API_KEY or NOTION_DATABASE_ID unset — skipping Notion notification")


def lambda_handler(event=None, context=None, *, dry_run: bool = False):
    """Lambda handler that generates the XSS intelligence report and delivers it to Discord/Notion."""
    logger.info("=== XSS Intel Agent start ===")
    config = get_xss_config()
    _preflight(config)

    if dry_run:
        logger.info("Dry-run mode — skipping the pipeline")
        return {"statusCode": 200, "body": "dry-run"}
    result: dict[str, object] = {}

    logger.info("generating XSS vulnerability report (WebSearch)...")
    try:
        report = generate_xss_report(config)
        logger.debug("report generated (length=%d)", len(report))
        result["generation"] = "ok"
    except Exception as e:
        logger.exception("report generation failed")
        result["generation"] = str(e)
        return {"statusCode": 500, "body": result}

    discord_ok = _is_configured(config.discord_token, config.discord_channel_id)
    notion_ok = _is_configured(config.notion_api_key, config.notion_database_id)

    if discord_ok:
        logger.info("sending to Discord...")
        try:
            send_to_discord(report, config.discord_token, config.discord_channel_id)
            result["discord"] = "ok"
        except Exception as e:
            logger.exception("Discord send failed")
            result["discord"] = str(e)
    else:
        logger.warning("DISCORD_TOKEN or CHANNEL_ID unset — skipping Discord notification")
        result["discord"] = "skipped"

    if notion_ok:
        logger.info("creating Notion page...")
        try:
            metrics = extract_xss_metrics(report)
            page_url = send_to_notion(
                report,
                config.notion_api_key,
                config.notion_database_id,
                title=f"XSS 脆弱性インテリジェンス — {date.today().strftime('%Y-%m-%d')}",
                tags=["agent"],
                extra_properties=metrics,
            )
            if page_url:
                logger.info("Notion page: %s", page_url)
            result["notion"] = page_url or "ok"
        except Exception as e:
            logger.exception("Notion send failed")
            result["notion"] = str(e)
    else:
        logger.warning("NOTION_API_KEY or NOTION_DATABASE_ID unset — skipping Notion notification")
        result["notion"] = "skipped"

    if not discord_ok or not notion_ok:
        filename = f"xss_intel_{date.today().strftime('%Y-%m-%d')}.md"
        path = _write_md_fallback(report, filename)
        logger.info("wrote MD file: %s", path)
        result["md_fallback"] = str(path)

    logger.info("=== done ===")

    notifier_values = [result.get("discord", "ok"), result.get("notion", "ok")]
    all_notifiers_failed = all(v not in ("ok", "skipped") and v is not None for v in notifier_values)
    status_code = 500 if all_notifiers_failed else 200
    return {"statusCode": status_code, "body": result}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="XSS Intel agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate credentials and config without running the pipeline")
    args = parser.parse_args()
    lambda_handler(dry_run=args.dry_run)
