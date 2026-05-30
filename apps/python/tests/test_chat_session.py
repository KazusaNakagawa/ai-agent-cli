"""Tests for src/chat_session.py — reusable chat session command builder."""
import uuid
from pathlib import Path

import pytest

from src import chat_session


class TestBuildCmd:
    def test_new_session_creates_session_file_with_uuid(self, tmp_path: Path):
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"

        chat_session.build_cmd("2026-05-16", briefing, session_file)

        assert session_file.exists()
        uuid.UUID(session_file.read_text().strip())  # raises if invalid

    def test_new_session_cmd_includes_session_id_name_and_context(self, tmp_path: Path):
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"

        cmd = chat_session.build_cmd("2026-05-16", briefing, session_file)

        assert cmd[0] == "claude"
        assert "--session-id" in cmd
        saved_id = session_file.read_text().strip()
        assert saved_id in cmd
        assert "--name" in cmd
        assert "briefing-chat-2026-05-16" in cmd
        assert "--append-system-prompt" in cmd
        prompt = cmd[cmd.index("--append-system-prompt") + 1]
        assert "本文テスト" in prompt
        assert "2026-05-16" in prompt

    def test_resume_session_uses_saved_id_and_omits_system_prompt(self, tmp_path: Path):
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"
        session_file.write_text("existing-uuid-abcd")

        cmd = chat_session.build_cmd("2026-05-16", briefing, session_file)

        assert "--resume" in cmd
        assert "existing-uuid-abcd" in cmd
        assert "--session-id" not in cmd
        assert "--append-system-prompt" not in cmd

    def test_resume_session_does_not_overwrite_session_file(self, tmp_path: Path):
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"
        session_file.write_text("existing-uuid-abcd")

        chat_session.build_cmd("2026-05-16", briefing, session_file)

        assert session_file.read_text().strip() == "existing-uuid-abcd"

    def test_build_cmd_does_not_print(self, tmp_path: Path, capsys):
        """The library function must be silent so SSE consumers don't get
        informational text bleeding into the response stream."""
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"

        chat_session.build_cmd("2026-05-16", briefing, session_file)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


class TestSessionNameFor:
    def test_session_name_format(self):
        assert chat_session.session_name_for("2026-05-16") == "briefing-chat-2026-05-16"
