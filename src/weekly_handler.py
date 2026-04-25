"""週次ブリーフィング振り返りページを Notion に作成するハンドラ。"""
from src.config import CONFIG
from src.generator.weekly_summary import generate_weekly_summary, week_label
from src.notifier.notion import fetch_weekly_pages, send_to_notion
from src.logger import get_logger

logger = get_logger(__name__)


def weekly_handler(event=None, context=None):
    """過去7日のブリーフィングを集約し、週次振り返りページを Notion に作成する。"""
    logger.info("=== 週次振り返り 開始 ===")

    logger.info("Notion から過去7日のページを取得中...")
    pages = fetch_weekly_pages(
        CONFIG.notion_api_key,
        CONFIG.notion_database_id,
        days=7,
    )

    if not pages:
        logger.warning("対象ページが見つかりませんでした。処理を終了します。")
        return {"statusCode": 204, "body": "No pages found."}

    logger.info("週次サマリー生成中 (%d ページ)...", len(pages))
    summary = generate_weekly_summary(pages)
    title = f"週次振り返り — {week_label()}"

    logger.info("Notion にページ作成中...")
    page_url = send_to_notion(
        summary,
        CONFIG.notion_api_key,
        CONFIG.notion_database_id,
        title=title,
        tags=["weekly-summary"],
    )

    if page_url:
        logger.info("Notion ページ: %s", page_url)

    logger.info("=== 完了 ===")
    return {"statusCode": 200, "body": f"Weekly summary posted: {page_url}"}
