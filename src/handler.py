from src.config import CONFIG
from src.fetcher.stocks import fetch_stock_moves
from src.generator.briefing import generate_briefing
from src.notifier.discord import send_to_discord
from src.logger import get_logger

logger = get_logger(__name__)


def lambda_handler(event=None, context=None):
    logger.info("=== My World Briefing 開始 ===")

    logger.info("株価取得中...")
    stocks = fetch_stock_moves(CONFIG.portfolio.tickers)

    logger.info("ブリーフィング生成中 (WebSearch)...")
    briefing = generate_briefing(stocks, CONFIG)

    logger.debug("ブリーフィング内容:\n%s", briefing)

    logger.info("Discord に送信中...")
    send_to_discord(briefing, CONFIG.discord_token, CONFIG.discord_channel_id)

    logger.info("=== 完了 ===")
    return {"statusCode": 200, "body": "Briefing sent."}
