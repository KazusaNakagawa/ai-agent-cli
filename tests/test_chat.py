"""Tests for bin/chat.py — session management and command building."""
import importlib.util
import uuid
from pathlib import Path

import pytest

# Import bin/chat.py without triggering main()
_spec = importlib.util.spec_from_file_location(
    "chat", Path(__file__).parents[1] / "bin" / "chat.py"
)
chat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chat)


class TestListSessions:
    def test_missing_dir_prints_no_sessions(self, tmp_path, capsys):
        chat.list_sessions(tmp_path / "nonexistent")
        assert "No saved sessions." in capsys.readouterr().out

    def test_empty_dir_prints_no_sessions(self, tmp_path, capsys):
        chat.list_sessions(tmp_path)
        assert "No saved sessions." in capsys.readouterr().out

    def test_lists_saved_sessions_sorted(self, tmp_path, capsys):
        (tmp_path / "2026-05-16").write_text("uuid-a")
        (tmp_path / "2026-05-17").write_text("uuid-b")
        chat.list_sessions(tmp_path)
        out = capsys.readouterr().out
        assert "2026-05-16  uuid-a" in out
        assert "2026-05-17  uuid-b" in out
        assert out.index("2026-05-16") < out.index("2026-05-17")


class TestBuildCmd:
    def test_new_session_creates_session_file(self, tmp_path):
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"

        chat.build_cmd("2026-05-16", briefing, session_file)

        assert session_file.exists()
        uuid.UUID(session_file.read_text().strip())  # raises if not valid UUID

    def test_new_session_cmd_includes_session_id_and_context(self, tmp_path):
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"

        cmd = chat.build_cmd("2026-05-16", briefing, session_file)

        assert cmd[0] == "claude"
        assert "--session-id" in cmd
        saved_id = session_file.read_text().strip()
        assert saved_id in cmd
        assert "--append-system-prompt" in cmd
        prompt = cmd[cmd.index("--append-system-prompt") + 1]
        assert "本文テスト" in prompt
        assert "2026-05-16" in prompt

    def test_resume_session_uses_saved_id_and_omits_system_prompt(self, tmp_path):
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"
        session_file.write_text("existing-uuid-abcd")

        cmd = chat.build_cmd("2026-05-16", briefing, session_file)

        assert "--session-id" in cmd
        assert "existing-uuid-abcd" in cmd
        assert "--append-system-prompt" not in cmd

    def test_new_session_includes_name(self, tmp_path):
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("内容")
        session_file = tmp_path / "2026-05-16"

        cmd = chat.build_cmd("2026-05-16", briefing, session_file)

        assert "--name" in cmd
        assert "briefing-chat-2026-05-16" in cmd

    def test_resume_session_includes_name(self, tmp_path):
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("内容")
        session_file = tmp_path / "2026-05-16"
        session_file.write_text("some-uuid")

        cmd = chat.build_cmd("2026-05-16", briefing, session_file)

        assert "--name" in cmd
        assert "briefing-chat-2026-05-16" in cmd
