import pytest

from src.evaluator import storage


def test_save_and_load_json_roundtrip(tmp_path):
    p = tmp_path / "a.json"
    storage.save_json(p, {"x": 1})
    assert storage.load_json(p) == {"x": 1}


def test_load_json_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        storage.load_json(tmp_path / "missing.json")


def test_list_briefing_dates_filters_and_sorts(tmp_path, monkeypatch):
    bdir = tmp_path / "briefing"
    bdir.mkdir()
    for name in [
        "briefing_2026-06-17.md",
        "briefing_2026-06-15.md",
        "local_2026-06-16.md",
        "briefing_2026-06-16-001.md",
        "briefing_2026-02-31.md",  # 形式は合うが暦上無効
    ]:
        (bdir / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(storage, "BRIEFING_OUTPUT_DIR", bdir)
    assert storage.list_briefing_dates() == ["2026-06-15", "2026-06-17"]
