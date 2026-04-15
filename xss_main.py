from src.config import XSS_CONFIG
from src.generator.xss_report import generate_xss_report
from src.notifier.discord import send_to_discord
from src.logger import get_logger

logger = get_logger(__name__)


def lambda_handler(event=None, context=None):
    logger.info("=== XSS Intel Agent 開始 ===")

    logger.info("XSS 脆弱性レポート生成中 (WebSearch)...")
    report = generate_xss_report(XSS_CONFIG)

    logger.debug("レポート内容:\n%s", report)

    logger.info("Discord に送信中...")
    send_to_discord(report, XSS_CONFIG.discord_token, XSS_CONFIG.discord_channel_id)

    logger.info("=== 完了 ===")
    return {"statusCode": 200, "body": "XSS Intel report sent."}


if __name__ == "__main__":
    lambda_handler()
