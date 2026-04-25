import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
from notion_client import Client
from src.logger import get_logger

logger = get_logger(__name__)

_CHAR_LIMIT = 2000
_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\)]+)\)")
_LABEL_COLON_RE = re.compile(r"^([-*]\s+)?([^：\n]{1,30}：)(.+)")
_LIST_TYPES = {"numbered_list_item", "bulleted_list_item"}
_INDENT_RE = re.compile(r"^( {2,}|\t)([-*]|\d+\.)\s+(.*)")


# ---------------------------------------------------------------------------
# Markdown → Notion rich_text / block 変換
# ---------------------------------------------------------------------------

def _parse_inline(text: str) -> list[dict]:
    """1行のインラインマークダウンを Notion rich_text オブジェクトのリストに変換。
    対応: **bold**, [label](url), それ以外はプレーンテキスト。
    2000文字制限を超えないようにチャンク分割も行う。
    """
    rich_texts: list[dict] = []
    pos = 0

    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            rich_texts.extend(_plain_chunks(text[pos:m.start()]))

        if m.group(1) is not None:
            rich_texts.extend(_plain_chunks(m.group(1), bold=True))
        else:
            rich_texts.extend(_link_chunks(m.group(2), m.group(3)))

        pos = m.end()

    if pos < len(text):
        rich_texts.extend(_plain_chunks(text[pos:]))

    return rich_texts or [{"type": "text", "text": {"content": ""}}]


def _plain_chunks(text: str, bold: bool = False) -> list[dict]:
    """2000文字ごとに分割したプレーンテキスト rich_text を返す。"""
    result = []
    for i in range(0, max(len(text), 1), _CHAR_LIMIT):
        chunk = text[i:i + _CHAR_LIMIT]
        item: dict = {"type": "text", "text": {"content": chunk}}
        if bold:
            item["annotations"] = {"bold": True}
        result.append(item)
    return result


def _link_chunks(label: str, url: str) -> list[dict]:
    """リンク付き rich_text を返す。ラベルが 2000文字を超える場合はチャンク分割する。"""
    result = []
    for i in range(0, max(len(label), 1), _CHAR_LIMIT):
        chunk = label[i:i + _CHAR_LIMIT]
        result.append({
            "type": "text",
            "text": {"content": chunk, "link": {"url": url}},
            "annotations": {"color": "blue"},
        })
    return result


# ---------------------------------------------------------------------------
# 行 → Notion ブロック変換
# ---------------------------------------------------------------------------

def _list_block(block_type: str, text: str) -> dict:
    """numbered_list_item / bulleted_list_item ブロックを生成する共通ファクトリ。"""
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": _parse_inline(text)},
    }


def _line_to_block(line: str) -> dict | None:
    """1行を Notion ブロック辞書に変換。空行・区切り線・見出し・リスト・段落を処理する。"""
    stripped = line.rstrip()

    if not stripped:
        return None

    if re.fullmatch(r"-{3,}", stripped):
        return {"object": "block", "type": "divider", "divider": {}}

    m = re.match(r"^(#{1,3})\s+(.*)", stripped)
    if m:
        level = len(m.group(1))
        block_type = f"heading_{min(level, 3)}"
        return {
            "object": "block",
            "type": block_type,
            block_type: {"rich_text": _parse_inline(m.group(2))},
        }

    m = re.match(r"^[-*]\s+(.*)", stripped)
    if m:
        return _list_block("bulleted_list_item", m.group(1))

    m = re.match(r"^\d+\.\s+(.*)", stripped)
    if m:
        return _list_block("numbered_list_item", m.group(1))

    return _paragraph_block(stripped)


def _paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _parse_inline(text)},
    }


def _is_table_row(line: str) -> bool:
    stripped = line.rstrip()
    return stripped.startswith("|") and stripped.endswith("|")


def _is_table_separator(line: str) -> bool:
    stripped = line.rstrip()
    return bool(re.fullmatch(r"[\|\s\-:]+", stripped) and "|" in stripped)


def _table_rows_to_block(rows: list[str]) -> dict:
    """連続する Markdown テーブル行を Notion table ブロックに変換する。"""
    data_rows = [r for r in rows if not _is_table_separator(r)]
    has_header = len(rows) >= 2 and _is_table_separator(rows[1])

    def parse_cells(row: str) -> list[list[dict]]:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        return [_parse_inline(c) for c in cells]

    table_width = max((len(parse_cells(r)) for r in data_rows), default=1)

    children = []
    for row in data_rows:
        cells = parse_cells(row)
        while len(cells) < table_width:
            cells.append([{"type": "text", "text": {"content": ""}}])
        children.append({
            "type": "table_row",
            "table_row": {"cells": cells},
        })

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": table_width,
            "has_column_header": has_header,
            "has_row_header": False,
            "children": children,
        },
    }


def _split_label_colon(line: str) -> list[str]:
    """「ラベル：内容」形式の行を2行に分割して返す。該当しない場合はそのまま返す。

    例: "- **AI・クラウド：**強い。..." → ["**AI・クラウド：**", "強い。..."]
    - 箇条書きプレフィックス（- / *）は除去する
    - 既存の ** マーカーは除去してから付け直す（二重 ** 防止）
    """
    m = _LABEL_COLON_RE.match(line.rstrip())
    if not m:
        return [line]
    label = m.group(2).strip("* ").rstrip("：:")
    content = re.sub(r"^\*+\s*|\s*\*+$", "", m.group(3).strip())
    return [f"**{label}**", content]


def _markdown_to_blocks(markdown: str) -> list[dict]:
    """Markdown 文字列を Notion ブロック辞書のリストに変換して返す。

    - Markdown テーブルは Notion table ブロックに変換する。
    - インデント付き箇条書き（2スペース/タブ + - や 1.）は直前のリストブロックの children に追加する。
    - 「ラベル：内容」行はラベルと内容を別ブロックに分割する（テーブル・インデント行は除く）。
    """
    blocks: list[dict] = []
    raw_lines = markdown.splitlines()
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]

        if _is_table_row(line) or _is_table_separator(line):
            table_lines = []
            while i < len(raw_lines) and (_is_table_row(raw_lines[i]) or _is_table_separator(raw_lines[i])):
                table_lines.append(raw_lines[i])
                i += 1
            blocks.append(_table_rows_to_block(table_lines))
            continue

        m = _INDENT_RE.match(line)
        if m:
            marker, text = m.group(2), m.group(3)
            block_type = "numbered_list_item" if marker[0].isdigit() else "bulleted_list_item"
            child = _list_block(block_type, text)
            if blocks and blocks[-1].get("type") in _LIST_TYPES:
                ptype = blocks[-1]["type"]
                blocks[-1][ptype].setdefault("children", []).append(child)
            else:
                blocks.append(child)
            i += 1
            continue

        for expanded in _split_label_colon(line):
            block = _line_to_block(expanded)
            if block is not None:
                blocks.append(block)
        i += 1
    return blocks


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

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
    blocks = _markdown_to_blocks(text)

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


def _fetch_page_text(notion: Client, page_id: str) -> str:
    """ページ全ブロックをテキストに変換して返す（ページネーション対応）。"""
    lines: list[str] = []
    cursor: str | None = None
    while True:
        kwargs: dict = {"block_id": page_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.blocks.children.list(**kwargs)
        for block in resp.get("results", []):
            block_type = block.get("type", "")
            if block_type == "table":
                # テーブル行は子ブロックとして格納されているため個別に取得する
                rows_resp = notion.blocks.children.list(block_id=block["id"])
                col_count = block.get("table", {}).get("table_width", 0)
                for i, row in enumerate(rows_resp.get("results", [])):
                    row_text = _block_to_text(row)
                    lines.append(row_text)
                    if i == 0 and col_count:
                        lines.append("| " + " | ".join(["---"] * col_count) + " |")
            else:
                line = _block_to_text(block)
                if line:
                    lines.append(line)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return "\n".join(lines)


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
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
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
        if page.get("created_time", "") < since:
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
