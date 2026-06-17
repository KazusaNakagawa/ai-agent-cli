from unittest.mock import patch

from src.evaluator import extract, storage

_LLM_OUT = """```json
[
  {"theme": "高PER株に逆風", "direction": "弱気",
   "targets": ["PLTR", "MSFT"], "horizon_days": 5, "type": "prediction"},
  {"theme": "防衛セクター需要長期化", "direction": "強気",
   "targets": ["NOC"], "type": "causal"}
]
```"""


def test_parse_claims_assigns_ids_and_defaults():
    claims = extract.parse_claims(_LLM_OUT, "2026-06-17")
    assert [c["id"] for c in claims] == ["2026-06-17-01", "2026-06-17-02"]
    assert claims[1]["horizon_days"] == 5  # default applied
    assert claims[0]["type"] == "prediction"


def test_parse_claims_bad_json_returns_empty():
    assert extract.parse_claims("not json at all", "2026-06-17") == []


def test_parse_claims_string_target_not_split_into_chars():
    raw = '[{"theme":"t","direction":"中立","targets":"トヨタ","type":"causal"}]'
    claims = extract.parse_claims(raw, "2026-06-17")
    assert claims[0]["targets"] == ["トヨタ"]


def test_parse_claims_non_numeric_horizon_defaults():
    raw = ('[{"theme":"t","direction":"中立","targets":["X"],'
           '"horizon_days":"soon","type":"prediction"}]')
    claims = extract.parse_claims(raw, "2026-06-17")
    assert claims[0]["horizon_days"] == 5


def test_extract_one_saves_claims(tmp_path, monkeypatch):
    bdir = tmp_path / "briefing"
    bdir.mkdir()
    (bdir / "briefing_2026-06-17.md").write_text("本文", encoding="utf-8")
    monkeypatch.setattr(storage, "BRIEFING_OUTPUT_DIR", bdir)
    monkeypatch.setattr(storage, "CLAIMS_DIR", tmp_path / "claims")
    with patch("src.evaluator.extract.run_claude", return_value=_LLM_OUT):
        claims = extract.extract_one("2026-06-17")
    assert len(claims) == 2
    saved = storage.load_json(tmp_path / "claims" / "2026-06-17.json")
    assert saved == claims
