import json

from src.fetcher import judgment_log


def _write_log(dir_, entries):
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / "judgments.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def test_fetch_new_entries_missing_log_returns_empty(tmp_path):
    assert judgment_log.fetch_new_entries(tmp_path) == []


def test_fetch_new_entries_no_watermark_returns_all(tmp_path):
    entries = [{"id": "j_1"}, {"id": "j_2"}]
    _write_log(tmp_path, entries)
    assert judgment_log.fetch_new_entries(tmp_path) == entries


def test_fetch_new_entries_respects_watermark_boundary(tmp_path):
    entries = [{"id": "j_1"}, {"id": "j_2"}, {"id": "j_3"}]
    _write_log(tmp_path, entries)
    judgment_log.write_watermark("j_2", tmp_path)
    assert judgment_log.fetch_new_entries(tmp_path) == [{"id": "j_3"}]


def test_fetch_new_entries_watermark_at_latest_returns_empty(tmp_path):
    entries = [{"id": "j_1"}, {"id": "j_2"}]
    _write_log(tmp_path, entries)
    judgment_log.write_watermark("j_2", tmp_path)
    assert judgment_log.fetch_new_entries(tmp_path) == []


def test_fetch_new_entries_unknown_watermark_returns_all(tmp_path):
    entries = [{"id": "j_1"}, {"id": "j_2"}]
    _write_log(tmp_path, entries)
    judgment_log.write_watermark("j_missing", tmp_path)
    assert judgment_log.fetch_new_entries(tmp_path) == entries


def test_read_watermark_missing_returns_none(tmp_path):
    assert judgment_log.read_watermark(tmp_path) is None


def test_write_then_read_watermark_roundtrip(tmp_path):
    judgment_log.write_watermark("j_20260701_001", tmp_path)
    assert judgment_log.read_watermark(tmp_path) == "j_20260701_001"
