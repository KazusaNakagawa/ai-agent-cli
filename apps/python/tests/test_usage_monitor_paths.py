"""Tests for real project paths in the monitor aggregation (#481).

Transcript directory names under ``~/.claude/projects/`` are a lossy
encoding of the project path (``/``, ``_`` and ``.`` all become ``-``), so
the path is recovered from the ``cwd`` field the transcripts carry.
"""
import json
from pathlib import Path

from src import usage_monitor


def _line(mid, cwd=None, ts="2026-07-10T03:00:00.000Z"):
    entry = {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "id": mid,
            "model": "claude-sonnet-5",
            "usage": {"input_tokens": 100, "output_tokens": 10},
        },
    }
    if cwd is not None:
        entry["cwd"] = cwd
    return json.dumps(entry)


# --- abbreviate_home ---


def test_abbreviate_home_replaces_the_home_prefix():
    home = Path("/Users/someone")
    assert usage_monitor.abbreviate_home("/Users/someone/work/english_learn_app", home) == (
        "~/work/english_learn_app"
    )


def test_abbreviate_home_leaves_paths_outside_home_absolute():
    home = Path("/Users/someone")
    assert usage_monitor.abbreviate_home("/home/node/mulmoclaude", home) == (
        "/home/node/mulmoclaude"
    )


def test_abbreviate_home_does_not_match_a_sibling_with_the_same_prefix():
    home = Path("/Users/someone")
    assert usage_monitor.abbreviate_home("/Users/someone-else/work", home) == (
        "/Users/someone-else/work"
    )


def test_abbreviate_home_maps_home_itself_to_tilde():
    assert usage_monitor.abbreviate_home("/Users/someone", Path("/Users/someone")) == "~"


def test_abbreviate_home_passes_through_an_empty_path():
    assert usage_monitor.abbreviate_home("", Path("/Users/someone")) == ""


# --- project path capture ---


def _project(root: Path, dirname: str, lines: list[str]) -> None:
    d = root / dirname
    d.mkdir(parents=True)
    (d / "s1.jsonl").write_text("\n".join(lines) + "\n")


def test_aggregate_records_the_cwd_of_each_project(tmp_path):
    root = tmp_path / "projects"
    _project(
        root,
        "-Users-someone-work-english-learn-app",
        [_line("a1", cwd="/Users/someone/work/english_learn_app")],
    )
    _project(root, "-home-node-mulmoclaude", [_line("b1", cwd="/home/node/mulmoclaude")])

    report = usage_monitor.aggregate(root)

    assert report.project_paths == {
        "-Users-someone-work-english-learn-app": "/Users/someone/work/english_learn_app",
        "-home-node-mulmoclaude": "/home/node/mulmoclaude",
    }


def test_aggregate_records_no_path_when_transcripts_carry_no_cwd(tmp_path):
    root = tmp_path / "projects"
    _project(root, "proj-a", [_line("a1")])

    report = usage_monitor.aggregate(root)

    assert report.by_project["proj-a"].tokens == 110
    assert report.project_paths == {}


def test_aggregate_ignores_a_blank_or_non_string_cwd(tmp_path):
    root = tmp_path / "projects"
    _project(root, "proj-a", [_line("a1", cwd=""), _line("a2", cwd=123)])

    report = usage_monitor.aggregate(root)

    assert report.project_paths == {}


def test_aggregate_keeps_the_first_cwd_seen_for_a_project(tmp_path):
    root = tmp_path / "projects"
    _project(
        root,
        "proj-a",
        [_line("a1", cwd="/Users/someone/work/app"), _line("a2", cwd="/tmp/moved")],
    )

    report = usage_monitor.aggregate(root)

    assert report.project_paths == {"proj-a": "/Users/someone/work/app"}


def test_aggregate_reads_cwd_from_lines_without_usage_fields(tmp_path):
    """Older transcripts put ``cwd`` on user lines that carry no usage."""
    root = tmp_path / "projects"
    _project(
        root,
        "proj-a",
        [
            json.dumps({"type": "user", "cwd": "/Users/someone/work/app"}),
            _line("a1"),
        ],
    )

    report = usage_monitor.aggregate(root)

    assert report.project_paths == {"proj-a": "/Users/someone/work/app"}
