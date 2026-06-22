import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

_REPORT_PATH = Path(__file__).parents[1] / "src" / "usage_report.py"
_spec = importlib.util.spec_from_file_location("usage_report", _REPORT_PATH)
usage_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(usage_report)


def _write_day(usage_dir: Path, day: datetime, records: list[dict]) -> None:
    usage_dir.mkdir(parents=True, exist_ok=True)
    path = usage_dir / f"{day.strftime('%Y%m%d')}-usage.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def test_build_summary_totals_per_label_per_day(tmp_path):
    usage_dir = tmp_path / "usage"
    today = datetime.now()
    _write_day(usage_dir, today, [
        {"label": "briefing", "input_tokens": 10, "output_tokens": 5,
         "cache_read_tokens": 2, "cache_creation_tokens": 1, "cost_usd": 0.01},
        {"label": "briefing", "input_tokens": 20, "output_tokens": 7,
         "cache_read_tokens": 3, "cache_creation_tokens": 4, "cost_usd": 0.02},
        {"label": "xss", "input_tokens": 3, "output_tokens": 1, "cost_usd": 0.005},
    ])

    summary = usage_report.build_summary(usage_dir, days=7)

    day = today.date().isoformat()
    assert summary[(day, "briefing")]["calls"] == 2
    assert summary[(day, "briefing")]["input_tokens"] == 30
    assert summary[(day, "briefing")]["output_tokens"] == 12
    assert summary[(day, "briefing")]["cache_read_tokens"] == 5
    assert summary[(day, "briefing")]["cache_creation_tokens"] == 5
    assert abs(summary[(day, "briefing")]["cost_usd"] - 0.03) < 1e-9
    assert summary[(day, "xss")]["calls"] == 1


def test_iter_records_skips_malformed_lines(tmp_path):
    usage_dir = tmp_path / "usage"
    usage_dir.mkdir(parents=True)
    path = usage_dir / f"{datetime.now().strftime('%Y%m%d')}-usage.jsonl"
    path.write_text(
        '{"label": "ok", "input_tokens": 5, "cost_usd": 0.01}\n'
        "not-json-garbage\n"
        "\n",
        encoding="utf-8",
    )

    summary = usage_report.build_summary(usage_dir, days=7)
    day = datetime.now().date().isoformat()
    assert summary[(day, "ok")]["calls"] == 1
    assert summary[(day, "ok")]["input_tokens"] == 5


def test_format_summary_renders_header_and_rows(tmp_path):
    usage_dir = tmp_path / "usage"
    _write_day(usage_dir, datetime.now(), [
        {"label": "briefing", "input_tokens": 10, "output_tokens": 5,
         "cache_read_tokens": 2, "cache_creation_tokens": 1, "cost_usd": 0.0123},
    ])
    summary = usage_report.build_summary(usage_dir, days=7)
    out = usage_report.format_summary(summary)

    lines = out.splitlines()
    assert "CACHE_C" in lines[0]  # cache_creation 列が出力される
    assert "COST_USD" in lines[0]
    assert "briefing" in lines[2]
    assert "0.0123" in lines[2]  # コストは小数4桁


def test_days_flag_excludes_old_files(tmp_path):
    usage_dir = tmp_path / "usage"
    old = datetime.now() - timedelta(days=10)
    _write_day(usage_dir, old, [{"label": "old", "input_tokens": 99, "cost_usd": 1.0}])
    _write_day(usage_dir, datetime.now(), [{"label": "new", "input_tokens": 1, "cost_usd": 0.0}])

    summary = usage_report.build_summary(usage_dir, days=7)
    labels = {label for (_day, label) in summary}
    assert "new" in labels
    assert "old" not in labels


def test_no_records_message(tmp_path):
    summary = usage_report.build_summary(tmp_path / "usage", days=7)
    assert usage_report.format_summary(summary) == "No usage records found."
