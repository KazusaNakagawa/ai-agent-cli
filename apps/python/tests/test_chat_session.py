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

    def test_new_session_injects_history_context_when_given(self, tmp_path: Path):
        """Cross-date RAG excerpts (#395) are appended to the system prompt
        alongside today's briefing, only at session-creation time."""
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"

        cmd = chat_session.build_cmd(
            "2026-05-16", briefing, session_file,
            history_context="[briefing_2026-05-01.md:1-10]\nNVDA surged 5%",
        )

        prompt = cmd[cmd.index("--append-system-prompt") + 1]
        assert "本文テスト" in prompt
        assert "NVDA surged 5%" in prompt

    def test_new_session_history_context_instructs_citing_source_file(self, tmp_path: Path):
        """The injected instruction must tell Claude to cite which excerpt
        (by filename/date) it drew each historical fact from, so multi-day
        answers stay traceable back to a specific briefing (user feedback
        after #395 shipped)."""
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"

        cmd = chat_session.build_cmd(
            "2026-05-16", briefing, session_file,
            history_context="[briefing_2026-05-01.md:1-10]\nNVDA surged 5%",
        )

        prompt = cmd[cmd.index("--append-system-prompt") + 1]
        assert "ファイル名" in prompt
        assert "出典" in prompt

    def test_new_session_without_history_context_omits_that_section(self, tmp_path: Path):
        """history_context defaults to None: existing callers (bin/chat.py)
        must see byte-identical behavior to before #395."""
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"

        cmd = chat_session.build_cmd("2026-05-16", briefing, session_file)

        prompt = cmd[cmd.index("--append-system-prompt") + 1]
        assert "過去ブリーフィング" not in prompt

    def test_resume_session_ignores_history_context(self, tmp_path: Path):
        """A resumed session already has its context baked in — passing
        history_context on resume must not change the resulting cmd."""
        briefing = tmp_path / "briefing_2026-05-16.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-05-16"
        session_file.write_text("existing-uuid-abcd")

        cmd = chat_session.build_cmd(
            "2026-05-16", briefing, session_file,
            history_context="should be ignored",
        )

        assert "--append-system-prompt" not in cmd

    def test_new_session_injects_vault_context_when_given(self, tmp_path: Path):
        """Obsidian vault excerpts are appended to the system prompt alongside
        today's briefing, only at session-creation time."""
        briefing = tmp_path / "briefing_2026-07-17.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-07-17"

        cmd = chat_session.build_cmd(
            "2026-07-17", briefing, session_file,
            vault_context="[notes/idea.md:1-10]\nvault excerpt",
        )

        prompt = cmd[cmd.index("--append-system-prompt") + 1]
        assert "本文テスト" in prompt
        assert "vault excerpt" in prompt
        assert "Obsidian ノートの関連抜粋" in prompt
        assert "obsidian_note_excerpts" in prompt  # wrap_untrusted label

    def test_new_session_without_vault_context_omits_that_section(self, tmp_path: Path):
        """vault_context defaults to None: existing callers must see
        byte-identical behavior to before the Obsidian integration."""
        briefing = tmp_path / "briefing_2026-07-17.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-07-17"

        cmd = chat_session.build_cmd("2026-07-17", briefing, session_file)

        prompt = cmd[cmd.index("--append-system-prompt") + 1]
        assert "Obsidian" not in prompt

    def test_resume_session_ignores_vault_context(self, tmp_path: Path):
        """A resumed session already has its context baked in — passing
        vault_context on resume must not change the resulting cmd."""
        briefing = tmp_path / "briefing_2026-07-17.md"
        briefing.write_text("本文テスト")
        session_file = tmp_path / "2026-07-17"
        session_file.write_text("existing-uuid-abcd")

        cmd = chat_session.build_cmd(
            "2026-07-17", briefing, session_file,
            vault_context="should be ignored",
        )

        assert "--append-system-prompt" not in cmd
        assert "--resume" in cmd

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


class TestBuildJournalCmd:
    """#414: pre-trusted write dirs let Journal chat actually save files
    instead of being silently denied by the claude CLI's headless -p mode."""

    def test_new_session_without_trusted_dirs_omits_permission_flags(self, tmp_path: Path):
        session_file = tmp_path / "2026-07-25"

        cmd = chat_session.build_journal_cmd("2026-07-25", "journal context", session_file)

        assert "--add-dir" not in cmd
        assert "--permission-mode" not in cmd

    def test_new_session_with_trusted_dirs_adds_add_dir_and_permission_mode(self, tmp_path: Path):
        session_file = tmp_path / "2026-07-25"

        cmd = chat_session.build_journal_cmd(
            "2026-07-25", "journal context", session_file,
            trusted_write_dirs=["/tmp/zenn-docs"],
        )

        assert "--permission-mode" in cmd
        assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
        assert "--add-dir" in cmd
        assert cmd[cmd.index("--add-dir") + 1] == "/tmp/zenn-docs"

    def test_new_session_with_multiple_trusted_dirs_adds_one_add_dir_each(self, tmp_path: Path):
        session_file = tmp_path / "2026-07-25"

        cmd = chat_session.build_journal_cmd(
            "2026-07-25", "journal context", session_file,
            trusted_write_dirs=["/tmp/a", "/tmp/b"],
        )

        assert cmd.count("--add-dir") == 2
        assert "/tmp/a" in cmd
        assert "/tmp/b" in cmd

    def test_resume_session_without_trusted_dirs_omits_permission_flags(self, tmp_path: Path):
        session_file = tmp_path / "2026-07-25"
        session_file.write_text("existing-uuid-abcd")

        cmd = chat_session.build_journal_cmd("2026-07-25", "journal context", session_file)

        assert "--add-dir" not in cmd
        assert "--permission-mode" not in cmd

    def test_resume_session_with_trusted_dirs_also_adds_permission_flags(self, tmp_path: Path):
        """The permission grant is a per-process CLI flag, not part of the
        persisted session, so it must be re-applied on every resume too."""
        session_file = tmp_path / "2026-07-25"
        session_file.write_text("existing-uuid-abcd")

        cmd = chat_session.build_journal_cmd(
            "2026-07-25", "journal context", session_file,
            trusted_write_dirs=["/tmp/zenn-docs"],
        )

        assert "--resume" in cmd
        assert "--permission-mode" in cmd
        assert "--add-dir" in cmd
        assert cmd[cmd.index("--add-dir") + 1] == "/tmp/zenn-docs"
