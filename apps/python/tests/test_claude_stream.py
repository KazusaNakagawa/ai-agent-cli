"""Unit tests for src.claude_stream — the stream-json output parser."""
import json

from src.claude_stream import StreamState, consume_stream_line


def _delta(text: str) -> str:
    return json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": text},
            },
        }
    )


def _result(**fields) -> str:
    return json.dumps({"type": "result", "subtype": "success", **fields})


def test_text_deltas_flush_on_newline_and_buffer_trailing():
    state = StreamState()
    assert consume_stream_line(_delta("hello "), state) == []
    # A newline completes the first line; the rest stays buffered.
    assert consume_stream_line(_delta("world\nbye"), state) == ["hello world"]
    assert state.text_buf == "bye"
    assert state.saw_text is True


def test_text_delta_with_multiple_newlines_emits_all_complete_lines():
    state = StreamState()
    # All complete lines (a, ' b') are returned; the trailing fragment stays buffered.
    result = consume_stream_line(_delta("a\n b\n c"), state)
    assert result == ["a", " b"]
    assert state.text_buf == " c"


def test_result_record_captures_usage():
    state = StreamState()
    consume_stream_line(_delta("answer"), state)
    usage = {"input_tokens": 3, "output_tokens": 5}
    consume_stream_line(
        _result(usage=usage, total_cost_usd=0.02, duration_ms=99, result="answer"),
        state,
    )
    assert state.usage == usage
    assert state.cost_usd == 0.02
    assert state.duration_ms == 99


def test_thinking_deltas_are_ignored():
    state = StreamState()
    line = json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "thinking_delta", "thinking": "hmm"},
            },
        }
    )
    assert consume_stream_line(line, state) == []
    assert state.saw_text is False
    assert state.text_buf == ""


def test_result_text_fallback_when_no_deltas():
    """Older CLI without partial messages: the result text is surfaced so the
    answer is never dropped."""
    state = StreamState()
    consume_stream_line(_result(result="the whole answer"), state)
    assert state.text_buf == "the whole answer"


def test_non_json_line_is_skipped():
    state = StreamState()
    assert consume_stream_line("not json", state) == []


def _tool_result(content) -> str:
    return json.dumps(
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": content}]},
        }
    )


def test_result_record_captures_raw_line():
    """The terminal result line is kept verbatim so a caller can reuse the
    existing --output-format json parsing path unchanged (#421)."""
    state = StreamState()
    line = _result(usage={"input_tokens": 1}, result="answer")
    consume_stream_line(line, state)
    assert state.result_raw == line


def test_result_raw_is_none_before_the_terminal_record():
    state = StreamState()
    consume_stream_line(_delta("partial"), state)
    assert state.result_raw is None


def test_api_error_tool_results_are_collected():
    """WebSearch overload surfaces as a tool_result, not a process failure, so
    it is invisible unless the stream is inspected (observed 2026-07-26: 6x
    529 inside one briefing call, only found in the CLI session transcript)."""
    state = StreamState()
    consume_stream_line(_tool_result("API Error: 529 Overloaded. Try again."), state)
    assert state.api_errors == ["API Error: 529 Overloaded. Try again."]


def test_api_errors_collected_from_block_list_content():
    """tool_result content may be a list of blocks rather than a bare string."""
    state = StreamState()
    consume_stream_line(
        _tool_result([{"type": "text", "text": "API Error: 500 Internal"}]), state
    )
    assert len(state.api_errors) == 1
    assert "500" in state.api_errors[0]


def test_successful_tool_results_are_not_collected():
    state = StreamState()
    consume_stream_line(_tool_result("Web search results for query: ..."), state)
    assert state.api_errors == []


def test_api_error_message_is_truncated():
    """Boundary: a huge tool_result must not blow up the log line."""
    state = StreamState()
    consume_stream_line(_tool_result("API Error: 529 " + "x" * 5000), state)
    assert len(state.api_errors[0]) <= 200
