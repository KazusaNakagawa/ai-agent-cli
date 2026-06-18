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
        logger.warning("DISCORD_TOKEN または CHANNEL_ID が未設定 — Discord 通知をスキップします")
    if not _is_configured(config.notion_api_key, config.notion_database_id):
        logger.warning("NOTION_API_KEY または NOTION_DATABASE_ID が未設定 — Notion 通知をスキップします")


def lambda_handler(event=None, context=None, *, dry_run: bool = False):
    """XSS インテリジェンスレポートを生成し Discord/Notion に配信する Lambda ハンドラ。"""
    logger.info("=== XSS Intel Agent 開始 ===")
    config = get_xss_config()
    _preflight(config)

    if dry_run:
        logger.info("Dry-run モード — パイプラインをスキップします")
        return {"statusCode": 200, "body": "dry-run"}
    result: dict[str, object] = {}

    logger.info("XSS 脆弱性レポート生成中 (WebSearch)...")
    try:
        report = generate_xss_report(config)
        logger.debug("レポート生成完了 (length=%d)", len(report))
        result["generation"] = "ok"
    except Exception as e:
        logger.exception("レポート生成に失敗しました")
        result["generation"] = str(e)
        return {"statusCode": 500, "body": result}

    discord_ok = _is_configured(config.discord_token, config.discord_channel_id)
    notion_ok = _is_configured(config.notion_api_key, config.notion_database_id)

    if discord_ok:
        logger.info("Discord に送信中...")
        try:
            send_to_discord(report, config.discord_token, config.discord_channel_id)
            result["discord"] = "ok"
        except Exception as e:
            logger.exception("Discord 送信に失敗しました")
            result["discord"] = str(e)
    else:
        logger.warning("DISCORD_TOKEN または CHANNEL_ID が未設定 — Discord 通知をスキップします")
        result["discord"] = "skipped"

    if notion_ok:
        logger.info("Notion にページ作成中...")
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
                logger.info("Notion ページ: %s", page_url)
            result["notion"] = page_url or "ok"
        except Exception as e:
            logger.exception("Notion 送信に失敗しました")
            result["notion"] = str(e)
    else:
        logger.warning("NOTION_API_KEY または NOTION_DATABASE_ID が未設定 — Notion 通知をスキップします")
        result["notion"] = "skipped"

    if not discord_ok or not notion_ok:
        filename = f"xss_intel_{date.today().strftime('%Y-%m-%d')}.md"
        path = _write_md_fallback(report, filename)
        logger.info("MD ファイルに出力しました: %s", path)
        result["md_fallback"] = str(path)

    logger.info("=== 完了 ===")

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
