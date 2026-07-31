from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
from notion_client import Client
from src.logger import get_logger
from src.notifier.markdown import markdown_to_notion_blocks

# Re-export for backward compatibility with existing tests and callers.
_markdown_to_blocks = markdown_to_notion_blocks

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Return the current UTC time (mockable in tests)."""
    return datetime.now(timezone.utc)


def _resolve_title_prop(notion: Client, database_id: str, sample_title: str) -> str | None:
    """Identify the title property key by trial. Return the working key, or None if all fail."""
    for candidate in ("Name", "title"):
        try:
            page = notion.pages.create(
                parent={"database_id": database_id},
                properties={candidate: {"title": [{"type": "text", "text": {"content": sample_title}}]}},
            )
            notion.pages.update(page["id"], archived=True)
            logger.debug("title property key determined: %r", candidate)
            return candidate
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _append_blocks(notion: Client, page_id: str, blocks: list[dict]) -> None:
    """Append blocks to an existing page, batching at the Notion 100-block limit."""
    for i in range(0, len(blocks), 100):
        try:
            notion.blocks.children.append(
                block_id=page_id,
                children=blocks[i:i + 100],
            )
        except Exception:
            logger.exception("failed to append Notion blocks (page_id=%s, index=%d)", page_id, i)


def _create_page(
    notion: Client,
    database_id: str,
    title: str,
    blocks: list[dict],
    tags: list[str] | None = None,
    extra_properties: dict | None = None,
) -> dict | None:
    """Create a page with title/blocks in a Notion database. Return the created page, or None on failure."""
    # Get the title property key via databases.retrieve. On failure, try name candidates in order.
    title_prop_name: str | None = None
    try:
        db = notion.databases.retrieve(database_id)
        properties = db.get("properties") or {}
        title_prop_name = next(
            (k for k, v in properties.items() if v.get("type") == "title"),
            None,
        )
    except Exception:
        logger.exception("failed to retrieve Notion database schema (database_id=%s)", database_id)

    if title_prop_name is None:
        title_prop_name = _resolve_title_prop(notion, database_id, title)
    if title_prop_name is None:
        logger.error("failed to identify the Notion title property (database_id=%s)", database_id)
        return None

    # The Notion API only accepts children 100 blocks at a time.
    first_batch = blocks[:100]
    remaining = blocks[100:]

    properties: dict = {
        title_prop_name: {
            "title": [{"type": "text", "text": {"content": title}}]
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
        logger.exception("failed to create Notion page (database_id=%s, title=%s)", database_id, title)
        return None

    _append_blocks(notion, response["id"], remaining)
    return response


def send_to_notion(
    text: str,
    api_key: str,
    database_id: str,
    title: str | None = None,
    tags: list[str] | None = None,
    extra_properties: dict | None = None,
) -> str:
    """Post the report as a new page in the Notion database. Return the created page URL."""
    if not api_key or not database_id:
        logger.error("NOTION_API_KEY or NOTION_DATABASE_ID unset")
        return ""

    notion = Client(auth=api_key)
    page_title = title or f"Report — {date.today().strftime('%Y-%m-%d')}"
    blocks = markdown_to_notion_blocks(text)

    response = _create_page(notion, database_id, page_title, blocks, tags, extra_properties)
    if not response:
        return ""

    page_url = response.get("url", "")
    logger.info("Notion page created: %s", page_url)
    return page_url


# ---------------------------------------------------------------------------
# For the weekly summary: page fetching
# ---------------------------------------------------------------------------

def _rich_text_to_str(rich_texts: list[dict]) -> str:
    return "".join(rt.get("text", {}).get("content", "") for rt in rich_texts)


def _block_to_text(block: dict) -> str:
    """Convert a Notion block dict to a Markdown line."""
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


def _paginate(call, base_kwargs: dict) -> list[dict]:
    """Centralize cursor pagination for the Notion API.

    ``call`` is a callable that takes kwargs including ``start_cursor`` and returns
    a response with ``has_more`` / ``next_cursor`` / ``results`` keys.
    """
    results: list[dict] = []
    cursor: str | None = None
    while True:
        kwargs = dict(base_kwargs)
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = call(**kwargs)
        results.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


def _fetch_blocks(notion: Client, block_id: str) -> list[dict]:
    """Paginate and return all child blocks of the given block."""
    return _paginate(notion.blocks.children.list, {"block_id": block_id, "page_size": 100})


def _fetch_page_text(notion: Client, page_id: str) -> str:
    """Convert all blocks of a page to text (pagination- and nesting-aware)."""
    def _collect(block_id: str) -> list[str]:
        lines: list[str] = []
        for block in _fetch_blocks(notion, block_id):
            block_type = block.get("type", "")
            if block_type == "table":
                # Table rows are stored as child blocks, so fetch them separately.
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
                # Recursively fetch nested child blocks (indented lists, etc.)
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


def _notion_client(api_key: str, database_id: str) -> Client | None:
    """Validate required credentials and build a Notion client, or None if unset."""
    if not api_key or not database_id:
        logger.error("NOTION_API_KEY or NOTION_DATABASE_ID unset")
        return None
    return Client(auth=api_key)


def _search_tagged_pages(notion: Client, database_id: str, tag: str) -> list[dict]:
    """Search all pages under `database_id` tagged `tag` (empty tag = no filter).

    Returns raw Notion page objects, newest ``last_edited_time`` first (the
    order ``notion.search`` sorts by). Date-range filtering is left to the
    caller — different callers filter on different timestamp fields
    (``fetch_weekly_pages`` on ``created_time``, ``fetch_commentable_pages``
    on ``last_edited_time``, #396).
    """
    # databases.query was removed in Notion API 2025-09-03, so use search instead.
    # parent.database_id and tag are filtered on the Python side.
    normalized_db_id = database_id.replace("-", "")
    try:
        all_results = _paginate(notion.search, {
            "filter": {"value": "page", "property": "object"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": 100,
        })
    except Exception:
        logger.exception("Notion search failed (database_id=%s)", database_id)
        return []

    filtered = []
    for page in all_results:
        parent = page.get("parent", {})
        if (parent.get("database_id") or "").replace("-", "") != normalized_db_id:
            continue
        if tag and tag not in _get_page_tags(page):
            continue
        filtered.append(page)
    return filtered


def _parse_notion_ts(raw: str) -> datetime | None:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def fetch_weekly_pages(
    api_key: str, database_id: str, days: int = 7, tag: str = "agent"
) -> list[dict]:
    """Fetch the last N days of tagged briefing pages from Notion and convert to text.

    Args:
        tag: Tags value to filter on (default "agent"). Empty string means no tag filter.

    Returns:
        [{"title": str, "date": str, "text": str, "page_id": str}, ...] (ascending by created date)
    """
    notion = _notion_client(api_key, database_id)
    if notion is None:
        return []
    since_dt = _utcnow() - timedelta(days=days)
    candidates = _search_tagged_pages(notion, database_id, tag)

    filtered = []
    for page in candidates:
        created_dt = _parse_notion_ts(page.get("created_time", ""))
        if created_dt is None or created_dt < since_dt:
            continue
        filtered.append(page)

    def _fetch(page: dict) -> dict:
        page_id = page["id"]
        try:
            text = _fetch_page_text(notion, page_id)
        except Exception:
            logger.exception("failed to fetch page body (page_id=%s)", page_id)
            text = ""
        title = _extract_page_title(page)
        created = page.get("created_time", "")[:10]
        logger.debug("fetched: %s (%s)", title, created)
        return {"title": title, "date": created, "text": text, "page_id": page_id}

    with ThreadPoolExecutor(max_workers=5) as pool:
        pages = list(pool.map(_fetch, filtered))

    pages.sort(key=lambda p: p["date"])
    logger.info("weekly pages fetched: %d", len(pages))
    return pages


def fetch_commentable_pages(
    api_key: str, database_id: str, days: int = 7, tag: str = "agent"
) -> list[dict]:
    """Tagged pages *edited* (not just created) within the last `days` days (#396).

    A wider net than ``fetch_weekly_pages``: a page created long ago still
    counts if it was edited recently — e.g. someone left a Notion comment on
    an old briefing this week. No page body is fetched; comment ingestion
    only needs page identity.

    Returns: [{"page_id": str, "title": str, "date": str}, ...]
    ``date`` is deliberately ``created_time`` (not ``last_edited_time``): it
    identifies which specific report a comment belongs to, matching
    ``fetch_weekly_pages``'s contract, whereas the edit date would just be
    "recently" for every result and add no information the filter didn't
    already establish.
    """
    notion = _notion_client(api_key, database_id)
    if notion is None:
        return []
    since_dt = _utcnow() - timedelta(days=days)
    candidates = _search_tagged_pages(notion, database_id, tag)

    out = []
    for page in candidates:
        edited_dt = _parse_notion_ts(page.get("last_edited_time", ""))
        if edited_dt is None:
            continue
        if edited_dt < since_dt:
            # Skip pages edited before the cutoff; don't assume candidates
            # are ordered by last_edited_time (avoids silently dropping
            # in-window pages if the search API's sort ever changes).
            continue
        out.append({
            "page_id": page["id"],
            "title": _extract_page_title(page),
            "date": page.get("created_time", "")[:10],
        })
    return out


def fetch_new_comments(
    api_key: str, pages: list[dict], seen_ids: set[str]
) -> list[dict]:
    """Fetch comments on `pages` (each needs "page_id"/"title"/"date") not
    already in `seen_ids`, skipping blank comments (#396).

    A per-page comment-fetch failure is logged and skipped so one bad page
    doesn't block comments on the others.

    Returns: [{"comment_id", "page_id", "page_title", "page_date", "text",
    "created_time"}, ...]
    """
    if not api_key or not pages:
        return []

    notion = Client(auth=api_key)
    out = []
    for page in pages:
        try:
            comments = _paginate(notion.comments.list, {"block_id": page["page_id"]})
        except Exception:
            logger.exception("failed to fetch comments (page_id=%s)", page["page_id"])
            continue
        for c in comments:
            cid = c.get("id")
            if not cid or cid in seen_ids:
                continue
            text = _rich_text_to_str(c.get("rich_text", []))
            if not text.strip():
                continue
            out.append({
                "comment_id": cid,
                "page_id": page["page_id"],
                "page_title": page["title"],
                "page_date": page["date"],
                "text": text,
                "created_time": c.get("created_time", ""),
            })
    return out


# ---------------------------------------------------------------------------
# For the sector-sweep recovery job: appending to an existing page
# ---------------------------------------------------------------------------

def append_to_page_by_title(
    text: str,
    api_key: str,
    database_id: str,
    title: str,
    tag: str = "agent",
) -> str:
    """Append Markdown to the existing page whose title equals ``title``.

    Used by the recovery job (#432) to complete a briefing page whose sector
    sweep was severed by a DarkWake sleep, instead of publishing a second page
    for the same day. Returns the page URL, or "" when no page matches.
    """
    notion = _notion_client(api_key, database_id)
    if notion is None:
        return ""

    for page in _search_tagged_pages(notion, database_id, tag):
        if _extract_page_title(page) != title:
            continue
        _append_blocks(notion, page["id"], markdown_to_notion_blocks(text))
        page_url = page.get("url", "")
        logger.info("appended to Notion page: %s", page_url)
        return page_url

    logger.warning("no Notion page titled %r found — nothing appended", title)
    return ""
