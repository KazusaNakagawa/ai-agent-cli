"""Parser for the claude CLI ``--output-format stream-json`` output.

Token-consuming streaming call sites (chat, journal, …) share one concern:
turn the per-line JSON stream into user-facing assistant text while capturing
the terminal ``result`` record's usage (token counts, cost, duration). This
module owns that concern so the parsing logic isn't duplicated per endpoint.

``StreamState`` accumulates partial assistant text into whole lines (so an
SSE client's join-by-newline contract is preserved) and stashes the final
usage. ``consume_stream_line`` feeds it one JSON line at a time.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

# Upstream API failures reach us as tool results inside a *successful* run: the
# WebSearch server tool answers with "API Error: 529 Overloaded." and the model
# simply retries the query. The process still exits 0, so these are invisible
# to any caller that only inspects the terminal result (#421).
_API_ERROR_RE = re.compile(r"API Error:\s*\d{3}")

# Cap on a collected error message; the full tool result can be arbitrarily long.
_API_ERROR_MAX_LENGTH = 200


class StreamState:
    """Accumulator for parsing a ``--output-format stream-json`` stream.

    Buffers partial assistant text into whole lines (so the SSE client's
    join-by-newline contract is preserved) and captures the final ``usage``
    record (token counts, cost, duration) for usage logging.
    """

    def __init__(self) -> None:
        self.text_buf = ""
        self.saw_text = False
        self.usage: dict | None = None
        self.cost_usd: float | None = None
        self.duration_ms: int | None = None
        # Verbatim terminal ``result`` line, so a caller can hand it to the
        # existing ``--output-format json`` parsing path unchanged.
        self.result_raw: str | None = None
        # "API Error: NNN" messages seen in tool results during the run.
        self.api_errors: list[str] = []


def _find_api_errors(obj: dict) -> list[str]:
    """Return "API Error: NNN" messages carried by this record's tool results.

    ``tool_result`` content is either a bare string or a list of content blocks
    depending on the tool, so both shapes are flattened before matching.
    """
    content = (obj.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    found = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        inner = block.get("content")
        if isinstance(inner, list):
            text = " ".join(
                b.get("text", "") for b in inner if isinstance(b, dict)
            )
        else:
            text = inner if isinstance(inner, str) else ""
        if _API_ERROR_RE.search(text):
            found.append(text[:_API_ERROR_MAX_LENGTH])
    return found


def consume_stream_line(line: str, state: StreamState) -> list[str]:
    """Parse one stream-json line, returning newly-completed text lines.

    Only user-facing assistant text (``text_delta``) is surfaced — thinking
    deltas, hook/system events, and tool use are ignored so the streamed
    output matches the pre-stream-json plain-text behavior. The final
    ``result`` record's usage is stashed on ``state``; if partial-message
    deltas never produced text (older CLI), the result text is used as a
    fallback so the answer is never dropped.
    """
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        logger.debug("stream-json: non-JSON line (truncated): %.120s", line)
        return []

    obj_type = obj.get("type")
    if obj_type == "stream_event":
        event = obj.get("event") or {}
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                state.saw_text = True
                state.text_buf += delta.get("text", "")
                parts = state.text_buf.split("\n")
                state.text_buf = parts.pop()
                return parts
    elif obj_type == "user":
        state.api_errors.extend(_find_api_errors(obj))
    elif obj_type == "result":
        state.result_raw = line
        usage = obj.get("usage")
        if isinstance(usage, dict):
            state.usage = usage
            state.cost_usd = obj.get("total_cost_usd")
            state.duration_ms = obj.get("duration_ms")
        if not state.saw_text and not state.text_buf:
            result_text = obj.get("result")
            if isinstance(result_text, str):
                # Split on newlines so multi-line results are line-buffered the
                # same way text_delta output is: all complete lines go directly
                # to the caller, the final partial fragment stays in text_buf.
                parts = result_text.split("\n")
                state.text_buf = parts.pop()
                return parts
    return []
