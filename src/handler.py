from datetime import date

from src.config import CONFIG
from src.fetcher.stocks import fetch_stock_moves
from src.generator.briefing import generate_briefing
from src.metrics.briefing import extract_briefing_metrics
from src.notifier.discord import send_to_discord
from src.notifier.notion import send_to_notion
from src.logger import get_logger

logger = get_logger(__name__)


def lambda_handler(event=None, context=None):
    """株価ブリーフィングを生成し Discord/Notion に配信する Lambda ハンドラ。"""
    logger.info("=== My World Briefing 開始 ===")

    logger.info("株価取得中...")
    stocks = fetch_stock_moves(CONFIG.portfolio.tickers)

    logger.info("ブリーフィング生成中 (WebSearch)...")
    briefing = generate_briefing(stocks, CONFIG)

    logger.debug("ブリーフィング生成完了 (length=%d)", len(briefing))

    logger.info("Discord に送信中...")
    send_to_discord(briefing, CONFIG.discord_token, CONFIG.discord_channel_id)

    logger.info("Notion にページ作成中...")
    metrics = extract_briefing_metrics(briefing, CONFIG.portfolio.tickers)
    page_url = send_to_notion(
        briefing,
        CONFIG.notion_api_key,
        CONFIG.notion_database_id,
        title=f"マーケットブリーフィング — {date.today().strftime('%Y-%m-%d')}",
        tags=["agent"],
        extra_properties=metrics,
    )
    if page_url:
        logger.info("Notion ページ: %s", page_url)

    logger.info("=== 完了 ===")
    return {"statusCode": 200, "body": "Briefing sent."}
