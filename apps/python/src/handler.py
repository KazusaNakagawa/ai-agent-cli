from datetime import date

from src.claude_runner import get_model
from src.config import CONFIG
from src.constants import BRIEFING_MD_RETENTION_DAYS, BRIEFING_OUTPUT_DIR
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
        logger.warning("DISCORD_TOKEN または CHANNEL_ID が未設定 — Discord 通知をスキップします")
    if not _is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id):
        logger.warning("NOTION_API_KEY または NOTION_DATABASE_ID が未設定 — Notion 通知をスキップします")


def lambda_handler(event=None, context=None, *, dry_run: bool = False):
    """株価ブリーフィングを生成し Discord/Notion/ローカル MD に配信する Lambda ハンドラ。"""
    logger.info("=== My World Briefing 開始 ===")
    _preflight()

    if dry_run:
        logger.info("Dry-run モード — パイプラインをスキップします")
        return {"statusCode": 200, "body": "dry-run"}

    logger.info("株価取得中...")
    stocks = fetch_stock_moves(CONFIG.portfolio.tickers)

    logger.info("ブリーフィング生成中 (WebSearch)...")
    briefing = generate_briefing(stocks, CONFIG)

    logger.debug("ブリーフィング生成完了 (length=%d)", len(briefing))

    discord_ok = _is_configured(CONFIG.discord_token, CONFIG.discord_channel_id)
    notion_ok = _is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id)

    # ローカル MD 出力を先に行う: Discord/Notion で例外が出ても本文をディスクに残せる
    md_written = False
    try:
        save_briefing_md(briefing, BRIEFING_OUTPUT_DIR, BRIEFING_MD_RETENTION_DAYS)
        md_written = True
    except OSError as exc:
        logger.warning("ローカル MD 出力失敗: %s — 継続します", exc)

    if discord_ok:
        logger.info("Discord に送信中...")
        send_to_discord(briefing, CONFIG.discord_token, CONFIG.discord_channel_id)

    if notion_ok:
        logger.info("Notion にページ作成中...")
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

    logger.info("=== 完了 ===")
    return {"statusCode": 200, "body": "Briefing sent.", "md_written": md_written}
