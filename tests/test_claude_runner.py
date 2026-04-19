import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.claude_runner import run_claude


def _make_result(returncode=0, stdout="output", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


class TestRunClaude:
    def test_cli_not_found_raises(self):
        with patch("src.claude_runner.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="claude CLI が見つかりません"):
                run_claude("prompt", "test")

    def test_success_returns_stripped_stdout(self):
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run", return_value=_make_result(stdout="  hello  \n")):
                result = run_claude("prompt", "test")
        assert result == "hello"

    def test_timeout_raises_runtime_error(self):
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "src.claude_runner.subprocess.run",
                side_effect=subprocess.TimeoutExpired("claude", 300),
            ):
                with pytest.raises(RuntimeError, match="タイムアウト"):
                    run_claude("prompt", "test", timeout=300)

    def test_nonzero_returncode_raises_with_stderr(self):
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "src.claude_runner.subprocess.run",
                return_value=_make_result(returncode=1, stdout="", stderr="auth error"),
            ):
                with pytest.raises(RuntimeError, match="auth error"):
                    run_claude("prompt", "test")

    def test_nonzero_returncode_falls_back_to_stdout(self):
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "src.claude_runner.subprocess.run",
                return_value=_make_result(returncode=1, stdout="stdout error", stderr=""),
            ):
                with pytest.raises(RuntimeError, match="stdout error"):
                    run_claude("prompt", "test")

    def test_long_error_is_truncated(self):
        long_stderr = "x" * 3000
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "src.claude_runner.subprocess.run",
                return_value=_make_result(returncode=1, stdout="", stderr=long_stderr),
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    run_claude("prompt", "test")
        assert "truncated" in str(exc_info.value)

    def test_api_key_excluded_from_subprocess_env(self):
        captured = {}

        def fake_run(args, **kwargs):
            captured["env"] = kwargs.get("env", {})
            return _make_result()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret-key"}):
            with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
                with patch("src.claude_runner.subprocess.run", side_effect=fake_run):
                    run_claude("prompt", "test")

        assert "ANTHROPIC_API_KEY" not in captured["env"]

    def test_stdin_is_devnull(self):
        captured = {}

        def fake_run(args, **kwargs):
            captured["stdin"] = kwargs.get("stdin")
            return _make_result()

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run", side_effect=fake_run):
                run_claude("prompt", "test")

        assert captured["stdin"] == subprocess.DEVNULL
