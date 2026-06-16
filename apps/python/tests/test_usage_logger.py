import json
from datetime import datetime, timedelta

from src import usage_logger


def test_log_usage_appends_one_jsonl_line(monkeypatch, tmp_path):
    usage_dir = tmp_path / "usage"
    monkeypatch.setattr(usage_logger, "USAGE_DIR", usage_dir)

    usage_logger.log_usage(
        label="briefing",
        usage={
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_input_tokens": 5,
            "cache_creation_input_tokens": 3,
        },
        cost_usd=0.0123,
        duration_ms=1500,
    )

    files = list(usage_dir.glob("*-usage.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    rec = json.loads(lines[0])
    assert rec["label"] == "briefing"
    assert rec["input_tokens"] == 10
    assert rec["output_tokens"] == 20
    assert rec["cache_read_tokens"] == 5
    assert rec["cache_creation_tokens"] == 3
    assert rec["cost_usd"] == 0.0123
    assert rec["duration_ms"] == 1500
    assert "timestamp" in rec


def test_log_usage_purges_files_older_than_retention(monkeypatch, tmp_path):
    """LOG_RETENTION_DAYS より古い *-usage.jsonl は log_usage 呼び出し時に削除される。"""
    usage_dir = tmp_path / "usage"
    usage_dir.mkdir()
    monkeypatch.setattr(usage_logger, "USAGE_DIR", usage_dir)

    retention = usage_logger.LOG_RETENTION_DAYS
    old_day = (datetime.now() - timedelta(days=retention + 2)).strftime("%Y%m%d")
    recent_day = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    old_file = usage_dir / f"{old_day}-usage.jsonl"
    recent_file = usage_dir / f"{recent_day}-usage.jsonl"
    old_file.write_text("{}\n", encoding="utf-8")
    recent_file.write_text("{}\n", encoding="utf-8")

    usage_logger.log_usage(label="x", usage={}, cost_usd=None, duration_ms=None)

    remaining = {p.name for p in usage_dir.glob("*-usage.jsonl")}
    assert old_file.name not in remaining
    assert recent_file.name in remaining


def test_log_usage_swallows_errors(monkeypatch, tmp_path):
    """記録に失敗しても例外を送出しない（本処理を止めない）。"""
    monkeypatch.setattr(usage_logger, "USAGE_DIR", tmp_path / "usage")
    # json.dumps が落ちるようにして書き込み前に例外を起こす
    monkeypatch.setattr(usage_logger.json, "dumps", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    usage_logger.log_usage(label="x", usage={}, cost_usd=None, duration_ms=None)  # 例外が出なければOK
