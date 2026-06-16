import json

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


def test_log_usage_swallows_errors(monkeypatch, tmp_path):
    """記録に失敗しても例外を送出しない（本処理を止めない）。"""
    monkeypatch.setattr(usage_logger, "USAGE_DIR", tmp_path / "usage")
    # json.dumps が落ちるようにして書き込み前に例外を起こす
    monkeypatch.setattr(usage_logger.json, "dumps", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    usage_logger.log_usage(label="x", usage={}, cost_usd=None, duration_ms=None)  # 例外が出なければOK
