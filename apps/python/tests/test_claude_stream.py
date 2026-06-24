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
