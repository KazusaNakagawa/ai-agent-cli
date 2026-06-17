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


def test_pie_block_is_mermaid():
    block = report.pie_block("type別", {"prediction": {"count": 2, "hit_rate": 0.75}})
    assert "```mermaid" in block and "pie" in block


def test_xychart_block_quotes_dates_and_comma_separates_values():
    block = report.xychart_block([
        {"date": "2026-06-17", "hit_rate": 0.5},
        {"date": "2026-06-19", "hit_rate": 1.0},
    ])
    assert 'x-axis ["2026-06-17", "2026-06-19"]' in block
    assert "line [0.5, 1.0]" in block
