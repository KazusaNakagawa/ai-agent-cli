"""Tests for src/judgment_ingest.py — recording Notion comments via the judge CLI (#396)."""
import subprocess
from unittest.mock import patch

import pytest

from src import judgment_ingest


def _comment(**overrides) -> dict:
    base = {
        "comment_id": "c1",
        "page_id": "p1",
        "page_title": "マーケットブリーフィング — 2026-07-14",
        "page_date": "2026-07-14",
        "text": "この分析はおかしい",
        "created_time": "2026-07-14T10:00:00.000Z",
    }
    base.update(overrides)
    return base


class TestJudgeAvailable:
    def test_true_when_binary_exists(self, tmp_path, monkeypatch):
        fake_judge = tmp_path / "judge"
        fake_judge.write_text("#!/bin/sh\n")
        monkeypatch.setattr(judgment_ingest, "JUDGE_BIN", fake_judge)
        assert judgment_ingest.judge_available() is True

    def test_false_when_binary_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(judgment_ingest, "JUDGE_BIN", tmp_path / "nonexistent-judge")
        assert judgment_ingest.judge_available() is False


class TestRecordCommentAsJudgment:
    def test_invokes_judge_note_with_domain_reason_context(self):
        with patch("src.judgment_ingest.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            ok = judgment_ingest.record_comment_as_judgment(_comment())

        assert ok is True
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == str(judgment_ingest.JUDGE_BIN)
        assert cmd[1] == "note"
        assert "--domain" in cmd
        assert cmd[cmd.index("--domain") + 1] == "brief-gen"
        assert "--reason" in cmd
        assert cmd[cmd.index("--reason") + 1] == "この分析はおかしい"
        assert "--context" in cmd
        context = cmd[cmd.index("--context") + 1]
        assert "2026-07-14" in context
        assert "マーケットブリーフィング — 2026-07-14" in context

    def test_blank_text_is_skipped_without_invoking_judge(self):
        with patch("src.judgment_ingest.subprocess.run") as mock_run:
            ok = judgment_ingest.record_comment_as_judgment(_comment(text="   "))
        assert ok is False
        mock_run.assert_not_called()

    def test_judge_nonzero_exit_returns_false(self):
        with patch("src.judgment_ingest.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ["judge"])
            ok = judgment_ingest.record_comment_as_judgment(_comment())
        assert ok is False

    def test_judge_missing_binary_returns_false(self):
        with patch("src.judgment_ingest.subprocess.run") as mock_run:
            mock_run.side_effect = OSError("no such file")
            ok = judgment_ingest.record_comment_as_judgment(_comment())
        assert ok is False

    def test_judge_timeout_returns_false(self):
        with patch("src.judgment_ingest.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["judge"], timeout=10)
            ok = judgment_ingest.record_comment_as_judgment(_comment())
        assert ok is False
