from unittest.mock import patch

from src.evaluator import score, storage

_DATES = ["2026-06-17", "2026-06-19", "2026-06-25"]


def test_followup_dates_window_inclusive_upper_exclusive_base():
    # base 6-17, horizon 5 -> (6-17, 6-22] -> only 6-19
    assert score.followup_dates("2026-06-17", 5, _DATES) == ["2026-06-19"]


def test_followup_dates_none_when_no_briefing_in_window():
    assert score.followup_dates("2026-06-17", 1, _DATES) == []


def test_parse_verdict_bad_json_is_unresolved():
    v = score.parse_verdict("garbage")
    assert v["verdict"] == "unresolved"


def test_score_claim_unresolved_without_followup():
    claim = {"id": "2026-06-17-01", "theme": "t", "direction": "弱気",
             "targets": ["PLTR"], "horizon_days": 1, "type": "prediction"}
    result = score.score_claim(claim, _DATES)
    assert result == {"id": "2026-06-17-01", "verdict": "unresolved",
                      "confidence": 0.0, "rationale": "no follow-up briefing in window"}


def test_score_claim_uses_judge_when_followup_exists(tmp_path, monkeypatch):
    bdir = tmp_path / "briefing"
    bdir.mkdir()
    (bdir / "briefing_2026-06-19.md").write_text("後日本文", encoding="utf-8")
    monkeypatch.setattr(storage, "BRIEFING_OUTPUT_DIR", bdir)
    claim = {"id": "2026-06-17-01", "theme": "t", "direction": "弱気",
             "targets": ["PLTR"], "horizon_days": 5, "type": "prediction"}
    judge_out = '{"verdict": "hit", "confidence": 0.7, "rationale": "ok"}'
    with patch("src.evaluator.score.run_claude", return_value=judge_out):
        result = score.score_claim(claim, _DATES)
    assert result["verdict"] == "hit"
    assert result["id"] == "2026-06-17-01"
