from unittest.mock import patch

import pytest

from src.generator.self_profile import (
    DIFF_MARKER,
    REPORT_MARKER,
    generate_self_profile_update,
    parse_response,
)


def _valid_response(report="今週の気づき", diff="恒常的な傾向"):
    return f"{REPORT_MARKER}\n{report}\n\n{DIFF_MARKER}\n{diff}\n"


def test_parse_response_splits_sections():
    report, diff = parse_response(_valid_response("report text", "diff text"))
    assert report == "report text"
    assert diff == "diff text"


def test_parse_response_raises_on_missing_markers():
    with pytest.raises(ValueError):
        parse_response("no markers here")


def test_parse_response_raises_when_markers_are_out_of_order():
    reversed_response = f"{DIFF_MARKER}\ndiff text\n\n{REPORT_MARKER}\nreport text\n"
    with pytest.raises(ValueError):
        parse_response(reversed_response)


def test_generate_self_profile_update_returns_none_for_no_new_entries():
    with patch("src.generator.self_profile.run_claude") as mock_run:
        result = generate_self_profile_update([], existing_profile="existing")
    assert result is None
    mock_run.assert_not_called()


def test_generate_self_profile_update_calls_run_claude_and_parses():
    with patch(
        "src.generator.self_profile.run_claude", return_value=_valid_response()
    ) as mock_run:
        result = generate_self_profile_update([{"id": "j_1"}], existing_profile=None)
    assert result == ("今週の気づき", "恒常的な傾向")
    mock_run.assert_called_once()


def test_generate_self_profile_update_retries_then_succeeds():
    with patch(
        "src.generator.self_profile.run_claude",
        side_effect=["garbage", _valid_response()],
    ) as mock_run:
        result = generate_self_profile_update([{"id": "j_1"}])
    assert result == ("今週の気づき", "恒常的な傾向")
    assert mock_run.call_count == 2
    retry_prompt = mock_run.call_args_list[1][0][0]
    assert "Your previous output was invalid" in retry_prompt


def test_generate_self_profile_update_raises_after_max_retries():
    with patch(
        "src.generator.self_profile.run_claude", return_value="garbage"
    ) as mock_run:
        with pytest.raises(ValueError):
            generate_self_profile_update([{"id": "j_1"}], max_retries=2)
    assert mock_run.call_count == 2


def test_generate_self_profile_update_rejects_max_retries_below_one():
    with patch("src.generator.self_profile.run_claude") as mock_run:
        with pytest.raises(ValueError):
            generate_self_profile_update([{"id": "j_1"}], max_retries=0)
    mock_run.assert_not_called()
