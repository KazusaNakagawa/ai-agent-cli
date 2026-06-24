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
    elif obj_type == "result":
        usage = obj.get("usage")
        if isinstance(usage, dict):
            state.usage = usage
            state.cost_usd = obj.get("total_cost_usd")
            state.duration_ms = obj.get("duration_ms")
        if not state.saw_text and not state.text_buf:
            result_text = obj.get("result")
            if isinstance(result_text, str):
                state.text_buf = result_text
    return []
