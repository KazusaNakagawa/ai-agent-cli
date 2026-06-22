from src.evaluator import report


def _claim(cid, ctype, targets):
    return {"id": cid, "type": ctype, "targets": targets,
            "theme": "t", "direction": "弱気", "horizon_days": 5}


def test_aggregate_hit_rate_with_partial_weight():
    claims = {
        "d1-01": _claim("d1-01", "prediction", ["PLTR"]),
        "d1-02": _claim("d1-02", "prediction", ["PLTR"]),
        "d1-03": _claim("d1-03", "causal", ["NOC"]),
    }
    scores = [
        {"id": "d1-01", "verdict": "hit"},
        {"id": "d1-02", "verdict": "partial"},
        {"id": "d1-03", "verdict": "unresolved"},  # excluded
    ]
    agg = report.aggregate(scores, claims)
    # prediction: (1.0 + 0.5) / 2 = 0.75 ; causal excluded (unresolved)
    assert agg["by_type"]["prediction"] == {"count": 2, "hit_rate": 0.75}
    assert "causal" not in agg["by_type"]
    assert agg["by_target"]["PLTR"] == {"count": 2, "hit_rate": 0.75}


def test_build_html_contains_scorecard_structure():
    agg = {
        "by_type": {"prediction": {"count": 2, "hit_rate": 0.75}},
        "by_target": {"PLTR": {"count": 2, "hit_rate": 0.75}},
        "by_date": [{"date": "2026-06-17", "hit_rate": 0.75}],
    }
    html = report._build_html(agg)
    assert "<!doctype html>" in html
    assert "ブリーフィング評価スコアカード" in html
    assert "prediction" in html
    assert "PLTR" in html
    assert "2026-06-17" in html


def test_build_report_writes_dated_and_latest(tmp_path, monkeypatch):
    from src.evaluator import storage
    monkeypatch.setattr(storage, "CLAIMS_DIR", tmp_path / "claims")
    monkeypatch.setattr(storage, "SCORES_DIR", tmp_path / "scores")
    monkeypatch.setattr(storage, "REPORT_PATH", tmp_path / "report.html")
    monkeypatch.setattr(storage, "REPORT_DIR", tmp_path / "reports")

    (tmp_path / "claims").mkdir()
    (tmp_path / "scores").mkdir()

    import json
    claim = {"id": "2026-06-17-01", "type": "prediction", "targets": ["PLTR"],
             "theme": "t", "direction": "強気", "horizon_days": 5}
    (tmp_path / "claims" / "2026-06-17.json").write_text(json.dumps([claim]))
    score = {"id": "2026-06-17-01", "verdict": "hit", "confidence": 0.9, "rationale": "r"}
    (tmp_path / "scores" / "2026-06-17.json").write_text(json.dumps([score]))

    report.build_report()

    assert (tmp_path / "report.html").exists()
    from datetime import date
    dated = tmp_path / "reports" / f"report_{date.today().isoformat()}.html"
    assert dated.exists()
    assert dated.read_text() == (tmp_path / "report.html").read_text()
