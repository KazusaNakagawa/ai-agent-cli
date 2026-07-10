"""Tests for scripts/token_usage_report.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import token_usage_report as tur  # noqa: E402
from claude_rates import RATES, usage_cost  # noqa: E402


def _line(
    mid: str | None = "msg_1",
    model: str = "claude-sonnet-5",
    inp: int = 100,
    out: int = 10,
    cw: int = 0,
    cr: int = 0,
    ts: str = "2026-07-10T03:00:00.000Z",
) -> str:
    msg: dict = {
        "model": model,
        "usage": {
            "input_tokens": inp,
            "output_tokens": out,
            "cache_creation_input_tokens": cw,
            "cache_read_input_tokens": cr,
        },
    }
    if mid is not None:
        msg["id"] = mid
    return json.dumps({"type": "assistant", "timestamp": ts, "message": msg})


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    return tmp_path / "projects"


# --- success ---


def test_aggregates_by_project_date_model(projects_root: Path):
    _write(
        projects_root / "proj-a" / "s1.jsonl",
        [
            _line(mid="a1", model="claude-sonnet-5", inp=100, out=10),
            _line(mid="a2", model="claude-haiku-4-5", inp=200, out=20, ts="2026-07-11T03:00:00.000Z"),
        ],
    )
    _write(projects_root / "proj-b" / "s2.jsonl", [_line(mid="b1", inp=50, out=5)])

    report = tur.aggregate(projects_root)

    assert report.total_tokens == 100 + 10 + 200 + 20 + 50 + 5
    assert set(report.by_project) == {"proj-a", "proj-b"}
    assert report.by_project["proj-a"].tokens == 330
    assert set(report.by_date) == {"2026-07-10", "2026-07-11"}
    assert report.by_model["claude-haiku-4-5"].tokens == 220
    expected_cost = usage_cost(
        {"input_tokens": 100, "output_tokens": 10}, "claude-sonnet-5"
    )
    assert report.by_model["claude-sonnet-5"].cost == pytest.approx(
        expected_cost + usage_cost({"input_tokens": 50, "output_tokens": 5}, "claude-sonnet-5")
    )


def test_dedupes_message_ids_across_files(projects_root: Path):
    # Same message id appears in two files of one project (resumed session).
    _write(projects_root / "proj-a" / "s1.jsonl", [_line(mid="dup", inp=100, out=10)])
    _write(projects_root / "proj-a" / "s2.jsonl", [_line(mid="dup", inp=100, out=10)])

    report = tur.aggregate(projects_root)

    assert report.total_tokens == 110


def test_date_range_filter(projects_root: Path):
    _write(
        projects_root / "proj-a" / "s1.jsonl",
        [
            _line(mid="m1", ts="2026-07-09T12:00:00.000Z"),
            _line(mid="m2", ts="2026-07-10T12:00:00.000Z"),
            _line(mid="m3", ts="2026-07-11T12:00:00.000Z"),
        ],
    )

    report = tur.aggregate(projects_root, since="2026-07-10", until="2026-07-10")

    assert set(report.by_date) == {"2026-07-10"}
    assert report.total_tokens == 110


# --- failure / robustness ---


def test_malformed_lines_and_unknown_models_are_tolerated(projects_root: Path, capsys):
    _write(
        projects_root / "proj-a" / "s1.jsonl",
        [
            "not json {{{",
            _line(mid="m1", model="claude-future-9", inp=100, out=10),
            _line(mid="m2", inp=50, out=5),
        ],
    )

    report = tur.aggregate(projects_root)

    err = capsys.readouterr().err
    assert "malformed" in err
    assert "claude-future-9" in err
    assert report.total_tokens == 165
    # Unknown model is tracked as unpriced, not silently $0-costed.
    assert "claude-future-9" in report.unpriced_models
    assert report.by_model["claude-future-9"].cost == 0.0


def test_unreadable_file_is_skipped(projects_root: Path, capsys):
    _write(projects_root / "proj-a" / "ok.jsonl", [_line(mid="m1", inp=100, out=10)])
    bad = projects_root / "proj-a" / "bad.jsonl"
    _write(bad, [_line(mid="m2")])
    bad.chmod(0o000)
    try:
        report = tur.aggregate(projects_root)
    finally:
        bad.chmod(0o644)

    assert "unreadable" in capsys.readouterr().err
    assert report.total_tokens == 110


def test_missing_root_exits_nonzero(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        tur.main([str(tmp_path / "nope")])
    assert exc.value.code != 0


# --- boundary ---


def test_empty_root_reports_zero(projects_root: Path):
    projects_root.mkdir(parents=True)
    report = tur.aggregate(projects_root)
    assert report.total_tokens == 0
    assert report.by_project == {}


def test_message_without_id_counted_per_line(projects_root: Path):
    _write(
        projects_root / "proj-a" / "s1.jsonl",
        [_line(mid=None, inp=10, out=1), _line(mid=None, inp=10, out=1)],
    )
    report = tur.aggregate(projects_root)
    assert report.total_tokens == 22


def test_cli_output_contains_tables_and_estimate_label(projects_root: Path, capsys):
    _write(projects_root / "proj-a" / "s1.jsonl", [_line(mid="m1")])

    tur.main([str(projects_root)])

    out = capsys.readouterr().out
    assert "proj-a" in out
    assert "2026-07-10" in out
    assert "claude-sonnet-5" in out
    assert "API-equivalent" in out


def test_rates_shared_with_sdd_script():
    import sdd_token_cost

    assert sdd_token_cost.RATES is RATES
