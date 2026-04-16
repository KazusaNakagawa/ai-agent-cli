from src.config import get_xss_config
from src.generator.xss_report import generate_xss_report
from src.notifier.discord import send_to_discord
from src.notifier.notion import send_to_notion
from src.logger import get_logger

logger = get_logger(__name__)


def lambda_handler(event=None, context=None):
    """XSS インテリジェンスレポートを生成し Discord/Notion に配信する Lambda ハンドラ。"""
    logger.info("=== XSS Intel Agent 開始 ===")
    config = get_xss_config()
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

    logger.info("Discord に送信中...")
    try:
        send_to_discord(report, config.discord_token, config.discord_channel_id)
        result["discord"] = "ok"
    except Exception as e:
        logger.exception("Discord 送信に失敗しました")
        result["discord"] = str(e)

    logger.info("Notion にページ作成中...")
    try:
        page_url = send_to_notion(
            report,
            config.notion_api_key,
            config.notion_database_id,
        )
        if page_url:
            logger.info("Notion ページ: %s", page_url)
        result["notion"] = page_url or "ok"
    except Exception as e:
        logger.exception("Notion 送信に失敗しました")
        result["notion"] = str(e)

    logger.info("=== 完了 ===")

    all_notifiers_failed = result.get("discord", "ok") != "ok" and result.get("notion", "ok") != "ok"
    status_code = 500 if all_notifiers_failed else 200
    return {"statusCode": status_code, "body": result}


if __name__ == "__main__":
    lambda_handler()
