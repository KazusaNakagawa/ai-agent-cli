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


def test_log_usage_keeps_old_files_by_default(monkeypatch, tmp_path):
    """Verifies: with rotation disabled (the shipped default), a usage file older
    than LOG_RETENTION_DAYS survives a log_usage() call.
    Why: the dashboard's "All time" range is only meaningful with full history —
    purging silently capped it at ~8 days (#428).
    """
    usage_dir = tmp_path / "usage"
    usage_dir.mkdir()
    monkeypatch.setattr(usage_logger, "USAGE_DIR", usage_dir)
    monkeypatch.setattr(usage_logger, "_last_purge_date", None)

    assert usage_logger.USAGE_LOG_ROTATION_ENABLED is False

    ancient_day = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
    ancient_file = usage_dir / f"{ancient_day}-usage.jsonl"
    ancient_file.write_text("{}\n", encoding="utf-8")

    usage_logger.log_usage(label="x", usage={}, cost_usd=None, duration_ms=None)

    assert ancient_file.exists()


def test_log_usage_purges_files_older_than_retention(monkeypatch, tmp_path):
    """Verifies: with rotation explicitly enabled, files older than
    LOG_RETENTION_DAYS are still deleted on log_usage().
    Why: retention must stay switchable, not be removed outright.
    """
    usage_dir = tmp_path / "usage"
    usage_dir.mkdir()
    monkeypatch.setattr(usage_logger, "USAGE_DIR", usage_dir)
    monkeypatch.setattr(usage_logger, "USAGE_LOG_ROTATION_ENABLED", True)
    monkeypatch.setattr(usage_logger, "_last_purge_date", None)  # 同日 memo をリセット

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


def test_purge_keeps_the_boundary_day(monkeypatch, tmp_path):
    """Verifies: the file dated exactly at the cutoff (today - LOG_RETENTION_DAYS)
    is kept, only strictly older ones are deleted.
    Why: pins the off-by-one so re-enabling rotation can't silently eat one extra day.
    """
    usage_dir = tmp_path / "usage"
    usage_dir.mkdir()
    monkeypatch.setattr(usage_logger, "USAGE_DIR", usage_dir)
    monkeypatch.setattr(usage_logger, "USAGE_LOG_ROTATION_ENABLED", True)
    monkeypatch.setattr(usage_logger, "_last_purge_date", None)

    retention = usage_logger.LOG_RETENTION_DAYS
    boundary_day = (datetime.now() - timedelta(days=retention)).strftime("%Y%m%d")
    just_older_day = (datetime.now() - timedelta(days=retention + 1)).strftime("%Y%m%d")
    boundary_file = usage_dir / f"{boundary_day}-usage.jsonl"
    just_older_file = usage_dir / f"{just_older_day}-usage.jsonl"
    boundary_file.write_text("{}\n", encoding="utf-8")
    just_older_file.write_text("{}\n", encoding="utf-8")

    usage_logger.log_usage(label="x", usage={}, cost_usd=None, duration_ms=None)

    assert boundary_file.exists()
    assert not just_older_file.exists()


def test_purge_runs_at_most_once_per_day(monkeypatch, tmp_path):
    """同日内の 2 回目以降の log_usage では _purge_old_logs を再実行しない。"""
    usage_dir = tmp_path / "usage"
    monkeypatch.setattr(usage_logger, "USAGE_DIR", usage_dir)
    monkeypatch.setattr(usage_logger, "USAGE_LOG_ROTATION_ENABLED", True)
    monkeypatch.setattr(usage_logger, "_last_purge_date", None)

    calls = {"n": 0}
    real_purge = usage_logger._purge_old_logs

    def counting_purge(d):
        calls["n"] += 1
        real_purge(d)

    monkeypatch.setattr(usage_logger, "_purge_old_logs", counting_purge)

    usage_logger.log_usage(label="a", usage={}, cost_usd=None, duration_ms=None)
    usage_logger.log_usage(label="b", usage={}, cost_usd=None, duration_ms=None)

    assert calls["n"] == 1


def test_log_usage_swallows_errors(monkeypatch, tmp_path):
    """記録に失敗しても例外を送出しない（本処理を止めない）。"""
    monkeypatch.setattr(usage_logger, "USAGE_DIR", tmp_path / "usage")
    # json.dumps が落ちるようにして書き込み前に例外を起こす
    monkeypatch.setattr(usage_logger.json, "dumps", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    usage_logger.log_usage(label="x", usage={}, cost_usd=None, duration_ms=None)  # 例外が出なければOK


def test_log_usage_from_result_logs_when_usage_present(monkeypatch):
    """A result record with a usage dict is forwarded to log_usage with its
    cost / duration fields."""
    captured = {}

    def fake_log_usage(label, usage, cost_usd, duration_ms):
        captured.update(
            label=label, usage=usage, cost_usd=cost_usd, duration_ms=duration_ms
        )

    monkeypatch.setattr(usage_logger, "log_usage", fake_log_usage)

    result = {
        "usage": {"input_tokens": 3, "output_tokens": 5},
        "total_cost_usd": 0.01,
        "duration_ms": 42,
    }
    assert usage_logger.log_usage_from_result("chat", result) is True
    assert captured["label"] == "chat"
    assert captured["usage"]["output_tokens"] == 5
    assert captured["cost_usd"] == 0.01
    assert captured["duration_ms"] == 42


def test_log_usage_from_result_noop_without_usage(monkeypatch):
    """No usage dict → returns False and never calls log_usage."""
    called = False

    def fake_log_usage(*a, **k):
        nonlocal called
        called = True

    monkeypatch.setattr(usage_logger, "log_usage", fake_log_usage)

    assert usage_logger.log_usage_from_result("chat", {"result": "hi"}) is False
    assert usage_logger.log_usage_from_result("chat", None) is False
    assert called is False
