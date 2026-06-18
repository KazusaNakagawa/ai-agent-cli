"""Markdown → Notion block conversion utilities."""

import re

from src.constants import (
    NOTION_CHAR_LIMIT,
    NOTION_HEADING_RE,
    NOTION_INDENT_RE,
    NOTION_INLINE_RE,
    NOTION_LABEL_COLON_RE,
    NOTION_LIST_TYPES,
)


def _parse_inline(text: str) -> list[dict]:
    """1行のインラインマークダウンを Notion rich_text オブジェクトのリストに変換。
    対応: **bold**, [label](url), それ以外はプレーンテキスト。
    2000文字制限を超えないようにチャンク分割も行う。
    """
    rich_texts: list[dict] = []
    pos = 0

    for m in NOTION_INLINE_RE.finditer(text):
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
    for i in range(0, max(len(text), 1), NOTION_CHAR_LIMIT):
        chunk = text[i:i + NOTION_CHAR_LIMIT]
        item: dict = {"type": "text", "text": {"content": chunk}}
        if bold:
            item["annotations"] = {"bold": True}
        result.append(item)
    return result


def _link_chunks(label: str, url: str) -> list[dict]:
    """リンク付き rich_text を返す。ラベルが 2000文字を超える場合はチャンク分割する。"""
    result = []
    for i in range(0, max(len(label), 1), NOTION_CHAR_LIMIT):
        chunk = label[i:i + NOTION_CHAR_LIMIT]
        result.append({
            "type": "text",
            "text": {"content": chunk, "link": {"url": url}},
            "annotations": {"color": "blue"},
        })
    return result


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

    m = re.match(r"^(#{1,})\s+(.*)", stripped)
    if m:
        level = len(m.group(1))
        block_type = f"heading_{min(level, 3)}"
        heading_text = re.sub(r"^#+\s*", "", m.group(2))
        heading_text = re.sub(r"\*+", "", heading_text).strip()
        return {
            "object": "block",
            "type": block_type,
            block_type: {"rich_text": _parse_inline(heading_text)},
        }

    m = re.fullmatch(r"\*\*(.+?)\*\*", stripped)
    if m:
        return {
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": _parse_inline(m.group(1))},
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
    m = NOTION_LABEL_COLON_RE.match(line.rstrip())
    if not m:
        return [line]
    label = m.group(2).strip("* ").rstrip("：:")
    if not label:
        return [line]
    content = re.sub(r"^\*+\s*|\s*\*+$", "", m.group(3).strip())
    return [f"**{label}**", content]


def markdown_to_notion_blocks(markdown: str) -> list[dict]:
    """Markdown 文字列を Notion ブロック辞書のリストに変換して返す。

    - Markdown テーブルは Notion table ブロックに変換する。
    - インデント付き箇条書き（2スペース/タブ + - や 1.）は直前のリストブロックの children に追加する。
    - 「ラベル：内容」行はラベルと内容を別ブロックに分割する（テーブル・インデント行は除く）。
    """
    markdown = re.sub(r"\*{4,}", "**", markdown)
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

        m = NOTION_INDENT_RE.match(line)
        if m:
            marker, text = m.group(2), m.group(3)
            block_type = "numbered_list_item" if marker[0].isdigit() else "bulleted_list_item"
            child = _list_block(block_type, text)
            if blocks and blocks[-1].get("type") in NOTION_LIST_TYPES:
                ptype = blocks[-1]["type"]
                blocks[-1][ptype].setdefault("children", []).append(child)
            else:
                blocks.append(child)
            i += 1
            continue

        is_heading = NOTION_HEADING_RE.match(line)
        expanded_lines = [line] if is_heading else _split_label_colon(line)
        for expanded in expanded_lines:
            block = _line_to_block(expanded)
            if block is not None:
                blocks.append(block)
        i += 1
    return blocks
