from datetime import date
from pathlib import Path

from src.claude_runner import get_model
from src.config import CONFIG
from src.fetcher.stocks import fetch_stock_moves
from src.generator.briefing import generate_briefing
from src.metrics.briefing import extract_briefing_metrics
from src.notifier.discord import send_to_discord
from src.notifier.notion import send_to_notion
from src.logger import get_logger

logger = get_logger(__name__)

_OUTPUT_DIR = Path(__file__).parents[1] / "output"


def _is_configured(*values: str) -> bool:
    return all(values)


def _write_md_fallback(text: str, filename: str) -> Path:
    _OUTPUT_DIR.mkdir(exist_ok=True)
    path = _OUTPUT_DIR / filename
    path.write_text(text, encoding="utf-8")
    return path


def lambda_handler(event=None, context=None):
    """株価ブリーフィングを生成し Discord/Notion に配信する Lambda ハンドラ。"""
    logger.info("=== My World Briefing 開始 ===")

    logger.info("株価取得中...")
    stocks = fetch_stock_moves(CONFIG.portfolio.tickers)

    logger.info("ブリーフィング生成中 (WebSearch)...")
    briefing = generate_briefing(stocks, CONFIG)

    logger.debug("ブリーフィング生成完了 (length=%d)", len(briefing))

    discord_ok = _is_configured(CONFIG.discord_token, CONFIG.discord_channel_id)
    notion_ok = _is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id)

    if discord_ok:
        logger.info("Discord に送信中...")
        send_to_discord(briefing, CONFIG.discord_token, CONFIG.discord_channel_id)
    else:
        logger.warning("DISCORD_TOKEN または CHANNEL_ID が未設定 — Discord 通知をスキップします")

    model = get_model()
    notion_text = briefing + f"\n\n---\nModel: {model}"

    if notion_ok:
        logger.info("Notion にページ作成中...")
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
    else:
        logger.warning("NOTION_API_KEY または NOTION_DATABASE_ID が未設定 — Notion 通知をスキップします")

    wrote_md = False
    if not discord_ok or not notion_ok:
        filename = f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
        path = _write_md_fallback(notion_text, filename)
        logger.info("MD ファイルに出力しました: %s", path)
        wrote_md = True

    logger.info("=== 完了 ===")
    return {"statusCode": 200, "body": "Briefing sent.", "md_fallback": wrote_md}
