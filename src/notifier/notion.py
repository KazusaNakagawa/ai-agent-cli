from datetime import date
from notion_client import Client
from src.logger import get_logger

logger = get_logger(__name__)

_NOTION_BLOCK_CHAR_LIMIT = 2000


def _split_to_paragraph_blocks(text: str) -> list[dict]:
    """Notion の rich_text は 2000 文字制限があるため段落ごとに分割"""
    blocks = []
    for paragraph in text.split("\n"):
        # 2000 文字を超える段落はさらに分割
        for i in range(0, max(len(paragraph), 1), _NOTION_BLOCK_CHAR_LIMIT):
            chunk = paragraph[i:i + _NOTION_BLOCK_CHAR_LIMIT]
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                },
            })
    return blocks


def send_to_notion(text: str, api_key: str, database_id: str, title: str | None = None) -> str:
    """Notion データベースに新規ページとしてレポートを投稿する。作成したページのURLを返す。"""
    if not api_key or not database_id:
        logger.error("NOTION_API_KEY または NOTION_DATABASE_ID が未設定")
        return ""

    notion = Client(auth=api_key)
    page_title = title or f"XSS Intel — {date.today().strftime('%Y-%m-%d')}"

    blocks = _split_to_paragraph_blocks(text)

    # Notion API は children を 100 ブロックずつしか受け付けない
    first_batch = blocks[:100]
    remaining = blocks[100:]

    response = notion.pages.create(
        parent={"database_id": database_id},
        properties={
            "title": {
                "title": [{"type": "text", "text": {"content": page_title}}]
            }
        },
        children=first_batch,
    )

    page_id = response["id"]

    # 残りのブロックを追記
    for i in range(0, len(remaining), 100):
        notion.blocks.children.append(
            block_id=page_id,
            children=remaining[i:i + 100],
        )

    page_url = response.get("url", "")
    logger.info("Notion ページ作成完了: %s", page_url)
    return page_url
