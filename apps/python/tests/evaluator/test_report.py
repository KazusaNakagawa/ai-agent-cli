import re

from src.evaluator import report, storage


def _claim(cid, ctype, targets):
    return {"id": cid, "type": ctype, "targets": targets,
            "theme": "t", "direction": "弱気", "horizon_days": 5}


def _hue(color: str) -> int:
    return int(re.search(r"hsla?\((\d+)", color).group(1))


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
    assert agg["by_type"]["prediction"] == {"count": 2, "hit_rate": 0.75}
    assert "causal" not in agg["by_type"]
    assert agg["by_target"]["PLTR"] == {"count": 2, "hit_rate": 0.75}


def test_color_higher_rate_is_greener():
    # hue 0 = red, 120 = green; higher hit_rate -> higher hue
    assert _hue(report._color(1.0)) > _hue(report._color(0.0))


def test_bar_html_width_matches_rate():
    html = report._bar_html(0.5)
    assert "width:50%" in html


def test_section_rows_sorts_by_count_then_rate_and_limits():
    rates = {
        "A": {"count": 1, "hit_rate": 1.0},
        "B": {"count": 3, "hit_rate": 0.2},
        "C": {"count": 3, "hit_rate": 0.9},
    }
    rows = report._section_rows(rates, top_n=2)
    # only top 2 by count; C before B (higher rate); A excluded
    assert rows.index("C") < rows.index("B")
    assert "A" not in rows


def test_build_report_writes_html(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLAIMS_DIR", tmp_path / "claims")
    monkeypatch.setattr(storage, "SCORES_DIR", tmp_path / "scores")
    monkeypatch.setattr(storage, "REPORT_PATH", tmp_path / "report.html")
    storage.save_json(storage.CLAIMS_DIR / "2026-06-15.json",
                      [_claim("2026-06-15-01", "prediction", ["PLTR"])])
    storage.save_json(storage.SCORES_DIR / "2026-06-15.json",
                      [{"id": "2026-06-15-01", "verdict": "hit"}])
    html = report.build_report()
    assert "<!doctype html>" in html.lower()
    assert "PLTR" in html
    assert (tmp_path / "report.html").exists()
