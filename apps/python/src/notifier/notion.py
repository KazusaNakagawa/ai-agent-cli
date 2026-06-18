from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
from notion_client import Client
from src.logger import get_logger
from src.notifier.markdown import markdown_to_notion_blocks

# Re-export for backward compatibility with existing tests and callers.
_markdown_to_blocks = markdown_to_notion_blocks

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """テストでモック可能な UTC 現在時刻を返す。"""
    return datetime.now(timezone.utc)


def _resolve_title_prop(notion: Client, database_id: str, sample_title: str) -> str | None:
    """タイトルプロパティのキー名を試行して特定する。成功したキー名を返し、全て失敗した場合は None を返す。"""
    for candidate in ("Name", "title"):
        try:
            page = notion.pages.create(
                parent={"database_id": database_id},
                properties={candidate: {"title": [{"type": "text", "text": {"content": sample_title}}]}},
            )
            notion.pages.update(page["id"], archived=True)
            logger.debug("タイトルプロパティキー確定: %r", candidate)
            return candidate
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def send_to_notion(
    text: str,
    api_key: str,
    database_id: str,
    title: str | None = None,
    tags: list[str] | None = None,
    extra_properties: dict | None = None,
) -> str:
    """Notion データベースに新規ページとしてレポートを投稿する。作成したページの URL を返す。"""
    if not api_key or not database_id:
        logger.error("NOTION_API_KEY または NOTION_DATABASE_ID が未設定")
        return ""

    notion = Client(auth=api_key)
    page_title = title or f"Report — {date.today().strftime('%Y-%m-%d')}"
    blocks = markdown_to_notion_blocks(text)

    # databases.retrieve でタイトルプロパティキーを取得。失敗時は名前候補を順に試す。
    title_prop_name: str | None = None
    try:
        db = notion.databases.retrieve(database_id)
        properties = db.get("properties") or {}
        title_prop_name = next(
            (k for k, v in properties.items() if v.get("type") == "title"),
            None,
        )
    except Exception:
        logger.exception("Notion データベーススキーマの取得に失敗しました (database_id=%s)", database_id)

    if title_prop_name is None:
        title_prop_name = _resolve_title_prop(notion, database_id, page_title)
    if title_prop_name is None:
        logger.error("Notion タイトルプロパティの特定に失敗しました (database_id=%s)", database_id)
        return ""

    # Notion API は children を 100 ブロックずつしか受け付けない
    first_batch = blocks[:100]
    remaining = blocks[100:]

    properties: dict = {
        title_prop_name: {
            "title": [{"type": "text", "text": {"content": page_title}}]
        }
    }
    if tags:
        properties["Tags"] = {"multi_select": [{"name": t} for t in tags]}
    if extra_properties:
        properties.update(extra_properties)

    try:
        response = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            children=first_batch,
        )
    except Exception:
        logger.exception("Notion ページ作成に失敗しました (database_id=%s, title=%s)", database_id, page_title)
        return ""

    page_id = response["id"]

    for i in range(0, len(remaining), 100):
        try:
            notion.blocks.children.append(
                block_id=page_id,
                children=remaining[i:i + 100],
            )
        except Exception:
            logger.exception("Notion ブロック追加に失敗しました (page_id=%s, index=%d)", page_id, i)

    page_url = response.get("url", "")
    logger.info("Notion ページ作成完了: %s", page_url)
    return page_url


# ---------------------------------------------------------------------------
# 週次サマリー用: ページ取得
# ---------------------------------------------------------------------------

def _rich_text_to_str(rich_texts: list[dict]) -> str:
    return "".join(rt.get("text", {}).get("content", "") for rt in rich_texts)


def _block_to_text(block: dict) -> str:
    """Notion ブロック辞書を Markdown 行に変換する。"""
    block_type = block.get("type", "")
    content = block.get(block_type, {})
    text = _rich_text_to_str(content.get("rich_text", []))

    if block_type.startswith("heading_"):
        level = int(block_type[-1])
        return "#" * level + f" {text}"
    if block_type == "bulleted_list_item":
        return f"- {text}"
    if block_type == "numbered_list_item":
        return f"1. {text}"
    if block_type == "divider":
        return "---"
    if block_type == "table_row":
        cells = content.get("cells", [])
        return "| " + " | ".join(_rich_text_to_str(cell) for cell in cells) + " |"
    return text


def _fetch_blocks(notion: Client, block_id: str) -> list[dict]:
    """指定ブロックの全子ブロックをページネーションして返す。"""
    results: list[dict] = []
    cursor: str | None = None
    while True:
        kwargs: dict = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.blocks.children.list(**kwargs)
        results.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


def _fetch_page_text(notion: Client, page_id: str) -> str:
    """ページ全ブロックをテキストに変換して返す（ページネーション・ネスト対応）。"""
    def _collect(block_id: str) -> list[str]:
        lines: list[str] = []
        for block in _fetch_blocks(notion, block_id):
            block_type = block.get("type", "")
            if block_type == "table":
                # テーブル行は子ブロックとして格納されているため個別に取得する
                has_header = block.get("table", {}).get("has_column_header", False)
                col_count = block.get("table", {}).get("table_width", 0)
                for i, row in enumerate(_fetch_blocks(notion, block["id"])):
                    lines.append(_block_to_text(row))
                    if i == 0 and has_header and col_count:
                        lines.append("| " + " | ".join(["---"] * col_count) + " |")
            else:
                line = _block_to_text(block)
                if line:
                    lines.append(line)
                # ネストした子ブロック（インデントリストなど）を再帰取得
                if block.get("has_children") and block_type not in ("table",):
                    lines.extend(_collect(block["id"]))
        return lines

    return "\n".join(_collect(page_id))


def _extract_page_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return _rich_text_to_str(prop.get("title", []))
    return "(無題)"


def _get_page_tags(page: dict) -> list[str]:
    prop = page.get("properties", {}).get("Tags", {})
    if prop.get("type") == "multi_select":
        return [opt["name"] for opt in prop.get("multi_select", [])]
    return []


def fetch_weekly_pages(
    api_key: str, database_id: str, days: int = 7, tag: str = "agent"
) -> list[dict]:
    """過去 N 日分の指定タグ付きブリーフィングページを Notion から取得してテキスト化する。

    Args:
        tag: 取得対象の Tags 値（デフォルト "agent"）。空文字の場合はタグ絞り込みなし。

    Returns:
        [{"title": str, "date": str, "text": str}, ...] (作成日昇順)
    """
    if not api_key or not database_id:
        logger.error("NOTION_API_KEY または NOTION_DATABASE_ID が未設定")
        return []

    notion = Client(auth=api_key)
    # Notion API 2025-09-03 では databases.query が廃止されたため search を使用。
    # parent.database_id・created_time・tag は Python 側でフィルタリングする。
    since_dt = _utcnow() - timedelta(days=days)
    normalized_db_id = database_id.replace("-", "")

    all_results: list[dict] = []
    cursor: str | None = None
    try:
        while True:
            kwargs: dict = {
                "filter": {"value": "page", "property": "object"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": 100,
            }
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = notion.search(**kwargs)
            all_results.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
    except Exception:
        logger.exception("Notion 検索に失敗しました (database_id=%s)", database_id)
        return []

    filtered = []
    for page in all_results:
        parent = page.get("parent", {})
        if (parent.get("database_id") or "").replace("-", "") != normalized_db_id:
            continue
        created_iso = page.get("created_time", "")
        if created_iso.endswith("Z"):
            created_iso = created_iso[:-1] + "+00:00"
        try:
            created_dt = datetime.fromisoformat(created_iso)
        except ValueError:
            continue
        if created_dt < since_dt:
            continue
        if tag and tag not in _get_page_tags(page):
            continue
        filtered.append(page)

    def _fetch(page: dict) -> dict:
        page_id = page["id"]
        try:
            text = _fetch_page_text(notion, page_id)
        except Exception:
            logger.exception("ページ本文の取得に失敗しました (page_id=%s)", page_id)
            text = ""
        title = _extract_page_title(page)
        created = page.get("created_time", "")[:10]
        logger.debug("取得済み: %s (%s)", title, created)
        return {"title": title, "date": created, "text": text}

    with ThreadPoolExecutor(max_workers=5) as pool:
        pages = list(pool.map(_fetch, filtered))

    pages.sort(key=lambda p: p["date"])
    logger.info("週次ページ取得完了: %d件", len(pages))
    return pages
