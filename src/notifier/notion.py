import re
from datetime import date
from notion_client import Client
from src.logger import get_logger

logger = get_logger(__name__)

_CHAR_LIMIT = 2000


# ---------------------------------------------------------------------------
# Markdown → Notion rich_text / block 変換
# ---------------------------------------------------------------------------

def _parse_inline(text: str) -> list[dict]:
    """
    1行のインラインマークダウンを Notion rich_text オブジェクトのリストに変換。
    対応: **bold**, [label](url), それ以外はプレーンテキスト。
    2000文字制限を超えないようにチャンク分割も行う。
    """
    rich_texts: list[dict] = []
    # **bold** と [label](url) を一緒に捉える
    pattern = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\)]+)\)")
    pos = 0

    for m in pattern.finditer(text):
        # マッチ前のプレーンテキスト
        if m.start() > pos:
            rich_texts.extend(_plain_chunks(text[pos:m.start()]))

        if m.group(1) is not None:
            # **bold**
            rich_texts.extend(_plain_chunks(m.group(1), bold=True))
        else:
            # [label](url)
            rich_texts.extend(_link_chunks(m.group(2), m.group(3)))

        pos = m.end()

    # 残りのプレーンテキスト
    if pos < len(text):
        rich_texts.extend(_plain_chunks(text[pos:]))

    return rich_texts or [{"type": "text", "text": {"content": ""}}]


def _plain_chunks(text: str, bold: bool = False) -> list[dict]:
    """2000文字ごとに分割したプレーンテキスト rich_text を返す。bold=True の場合は太字アノテーションを付与する。"""
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

def _line_to_block(line: str) -> dict | None:
    """1行を Notion ブロック辞書に変換。空行・区切り線・見出し・リスト・段落を処理する。"""
    stripped = line.rstrip()

    # 空行 → スキップ（None を返して呼び出し元でフィルタ）
    if not stripped:
        return None

    # 水平線 --- → divider
    if re.fullmatch(r"-{3,}", stripped):
        return {"object": "block", "type": "divider", "divider": {}}

    # テーブル区切り行 |---|---| → スキップ
    if re.fullmatch(r"[\|\s\-:]+", stripped) and "|" in stripped:
        return None

    # 見出し ##
    m = re.match(r"^(#{1,3})\s+(.*)", stripped)
    if m:
        level = len(m.group(1))
        block_type = f"heading_{min(level, 3)}"
        return {
            "object": "block",
            "type": block_type,
            block_type: {"rich_text": _parse_inline(m.group(2))},
        }

    # テーブル行 | col | col | → 簡易的に段落として処理
    if stripped.startswith("|"):
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        plain = "  |  ".join(cells)
        return _paragraph_block(plain)

    # 箇条書き - item
    m = re.match(r"^[-*]\s+(.*)", stripped)
    if m:
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _parse_inline(m.group(1))},
        }

    # 番号付きリスト 1. item
    m = re.match(r"^\d+\.\s+(.*)", stripped)
    if m:
        return {
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": _parse_inline(m.group(1))},
        }

    return _paragraph_block(stripped)


def _paragraph_block(text: str) -> dict:
    """テキストを Notion paragraph ブロック辞書に変換して返す。"""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _parse_inline(text)},
    }


def _markdown_to_blocks(markdown: str) -> list[dict]:
    """Markdown 文字列を Notion ブロック辞書のリストに変換して返す。"""
    blocks = []
    for line in markdown.splitlines():
        block = _line_to_block(line)
        if block is not None:
            blocks.append(block)
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

def send_to_notion(text: str, api_key: str, database_id: str, title: str | None = None) -> str:
    """Notion データベースに新規ページとしてレポートを投稿する。作成したページの URL を返す。"""
    if not api_key or not database_id:
        logger.error("NOTION_API_KEY または NOTION_DATABASE_ID が未設定")
        return ""

    notion = Client(auth=api_key)
    page_title = title or f"XSS Intel — {date.today().strftime('%Y-%m-%d')}"
    blocks = _markdown_to_blocks(text)

    # データベーススキーマからタイトルプロパティのキーを取得。
    # properties が返らない場合は一般的なキー名にフォールバックする。
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
        # スキーマ取得不可の場合は一般的なキー名を順に試す
        title_prop_name = _resolve_title_prop(notion, database_id, page_title)
    if title_prop_name is None:
        logger.error("Notion タイトルプロパティの特定に失敗しました (database_id=%s)", database_id)
        return ""

    # Notion API は children を 100 ブロックずつしか受け付けない
    first_batch = blocks[:100]
    remaining = blocks[100:]

    try:
        response = notion.pages.create(
            parent={"database_id": database_id},
            properties={
                title_prop_name: {
                    "title": [{"type": "text", "text": {"content": page_title}}]
                }
            },
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
