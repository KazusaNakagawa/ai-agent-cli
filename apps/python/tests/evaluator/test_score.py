import json
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


def test_parse_verdict_non_numeric_confidence_defaults():
    v = score.parse_verdict('{"verdict":"hit","confidence":"high","rationale":"r"}')
    assert v["verdict"] == "hit"
    assert v["confidence"] == 0.0


def test_parse_verdicts_batch_valid():
    raw = '[{"id":"2026-06-17-01","verdict":"hit","confidence":0.8,"rationale":"ok"}]'
    results = score.parse_verdicts_batch(raw)
    assert results is not None
    assert results[0]["verdict"] == "hit"
    assert results[0]["id"] == "2026-06-17-01"


def test_parse_verdicts_batch_invalid_returns_none():
    assert score.parse_verdicts_batch("garbage") is None
    assert score.parse_verdicts_batch('{"verdict":"hit"}') is None  # object not array


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
    batch_out = '[{"id":"2026-06-17-01","verdict":"hit","confidence":0.7,"rationale":"ok"}]'
    with patch("src.evaluator.score.run_claude", return_value=batch_out):
        result = score.score_claim(claim, _DATES)
    assert result["verdict"] == "hit"
    assert result["id"] == "2026-06-17-01"


def test_score_claims_batch_single_call(tmp_path, monkeypatch):
    """同一 followup を持つ 2 件の claim が 1 回の run_claude で処理される。"""
    bdir = tmp_path / "briefing"
    bdir.mkdir()
    (bdir / "briefing_2026-06-19.md").write_text("後日本文", encoding="utf-8")
    monkeypatch.setattr(storage, "BRIEFING_OUTPUT_DIR", bdir)
    claims = [
        {"id": "2026-06-17-01", "theme": "t1", "direction": "強気",
         "targets": ["PLTR"], "horizon_days": 5, "type": "prediction"},
        {"id": "2026-06-17-02", "theme": "t2", "direction": "弱気",
         "targets": ["NVDA"], "horizon_days": 5, "type": "prediction"},
    ]
    batch_out = json.dumps([
        {"id": "2026-06-17-01", "verdict": "hit", "confidence": 0.9, "rationale": "r1"},
        {"id": "2026-06-17-02", "verdict": "miss", "confidence": 0.6, "rationale": "r2"},
    ])
    with patch("src.evaluator.score.run_claude", return_value=batch_out) as mock_run:
        results = score.score_claims_batch(claims, _DATES)
    assert mock_run.call_count == 1
    assert len(results) == 2
    assert results[0]["verdict"] == "hit"
    assert results[1]["verdict"] == "miss"


def test_score_claims_batch_fallback_on_bad_response(tmp_path, monkeypatch):
    """バッチ応答が壊れていたら per-claim フォールバックが走る。"""
    bdir = tmp_path / "briefing"
    bdir.mkdir()
    (bdir / "briefing_2026-06-19.md").write_text("後日本文", encoding="utf-8")
    monkeypatch.setattr(storage, "BRIEFING_OUTPUT_DIR", bdir)
    claims = [
        {"id": "2026-06-17-01", "theme": "t", "direction": "強気",
         "targets": ["PLTR"], "horizon_days": 5, "type": "prediction"},
    ]
    single_out = json.dumps([
        {"id": "2026-06-17-01", "verdict": "partial", "confidence": 0.5, "rationale": "fb"},
    ])
    # 1回目(バッチ)は壊れたJSON、2回目(フォールバック)は正常
    with patch("src.evaluator.score.run_claude", side_effect=["garbage", single_out]):
        results = score.score_claims_batch(claims, _DATES)
    assert results[0]["verdict"] == "partial"
