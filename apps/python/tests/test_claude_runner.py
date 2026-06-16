import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src import claude_runner, credentials, state as state_mod
from src.claude_runner import run_claude


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    """Pin state file so test runs are independent of the user's ~/.ai-agent/state.json."""
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "state.json")


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


class TestRunClaudeUsageLogging:
    def test_json_output_returns_result_text_and_logs_usage(self):
        """--output-format json の stdout から result を取り出して返し、
        usage を usage_logger に渡す。"""
        payload = json.dumps({
            "result": "  the answer  ",
            "total_cost_usd": 0.05,
            "duration_ms": 1200,
            "usage": {
                "input_tokens": 11,
                "output_tokens": 22,
                "cache_read_input_tokens": 3,
                "cache_creation_input_tokens": 4,
            },
        })
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run", return_value=_make_result(stdout=payload)):
                with patch("src.claude_runner.log_usage") as mock_log:
                    result = run_claude("prompt", "briefing")

        assert result == "the answer"
        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["label"] == "briefing"
        assert kwargs["usage"]["input_tokens"] == 11
        assert kwargs["cost_usd"] == 0.05
        assert kwargs["duration_ms"] == 1200

    def test_malformed_output_falls_back_to_stdout_without_logging(self):
        """JSON でない stdout はそのまま（strip して）返し、例外を出さず使用量も記録しない。"""
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run", return_value=_make_result(stdout="  plain text  ")):
                with patch("src.claude_runner.log_usage") as mock_log:
                    result = run_claude("prompt", "test")

        assert result == "plain text"
        mock_log.assert_not_called()

    def test_json_without_usage_returns_result_and_skips_logging(self):
        payload = json.dumps({"result": "ok"})
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run", return_value=_make_result(stdout=payload)):
                with patch("src.claude_runner.log_usage") as mock_log:
                    result = run_claude("prompt", "test")

        assert result == "ok"
        mock_log.assert_not_called()

    def test_json_without_result_field_falls_back_to_stdout(self):
        """result フィールドの無い JSON は raw stdout にフォールバックし、使用量も記録しない。"""
        payload = json.dumps({"foo": 1})
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run", return_value=_make_result(stdout=payload)):
                with patch("src.claude_runner.log_usage") as mock_log:
                    result = run_claude("prompt", "test")

        assert result == payload
        mock_log.assert_not_called()

    def test_non_string_result_is_stringified_and_usage_logged(self):
        """result が文字列以外でも str() 化して返し、usage は記録する。"""
        payload = json.dumps({"result": ["x", "y"], "usage": {"input_tokens": 5, "output_tokens": 6}})
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run", return_value=_make_result(stdout=payload)):
                with patch("src.claude_runner.log_usage") as mock_log:
                    result = run_claude("prompt", "test")

        assert result == str(["x", "y"])
        mock_log.assert_called_once()


class TestRunClaudeRetry:
    def test_retries_on_529_overloaded_and_succeeds(self):
        """Verifies: a 529 Overloaded on the first call triggers one retry and
        the second call's stdout is returned.
        Why: this is the exact failure mode that broke the scheduled job on
        2026-05-19. Without this behavior the run aborts and requires manual
        rerun.
        """
        error_result = _make_result(returncode=1, stderr="API Error: 529 Overloaded.")
        success_result = _make_result(returncode=0, stdout="recovered")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.time.sleep") as mock_sleep:
                with patch(
                    "src.claude_runner.subprocess.run",
                    side_effect=[error_result, success_result],
                ) as mock_run:
                    result = run_claude("prompt", "test")

        assert result == "recovered"
        assert mock_run.call_count == 2
        assert mock_sleep.call_count == 1

    def test_retries_on_socket_close(self):
        """Verifies: the node-fetch 'socket connection was closed unexpectedly'
        message (no HTTP code) is detected as transient and retried.
        Why: regression for the weekly job failure on 2026-06-05. Previously
        the classifier only matched 5xx codes, so this short-circuited after
        a single attempt and required manual rerun.
        """
        error_result = _make_result(
            returncode=1,
            stdout="API Error: The socket connection was closed unexpectedly. "
            "For more information, pass `verbose: true` in the second argument to fetch()",
        )
        success_result = _make_result(returncode=0, stdout="recovered")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.time.sleep"):
                with patch(
                    "src.claude_runner.subprocess.run",
                    side_effect=[error_result, success_result],
                ) as mock_run:
                    result = run_claude("prompt", "test")

        assert result == "recovered"
        assert mock_run.call_count == 2

    def test_retries_on_503_in_stdout(self):
        """Verifies: a 5xx error written to stdout (not stderr) is still
        detected and retried.
        Why: the claude CLI prints API errors to stdout, so the detector must
        scan both streams. Missing this would silently disable retry in
        practice.
        """
        error_result = _make_result(returncode=1, stdout="API Error: 503 Service Unavailable", stderr="")
        success_result = _make_result(returncode=0, stdout="ok")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.time.sleep"):
                with patch(
                    "src.claude_runner.subprocess.run",
                    side_effect=[error_result, success_result],
                ) as mock_run:
                    result = run_claude("prompt", "test")

        assert result == "ok"
        assert mock_run.call_count == 2

    def test_retries_exhausted_raises(self):
        """Verifies: when every attempt returns a transient 5xx, RuntimeError
        is raised after exactly max_attempts (3) subprocess calls.
        Why: bounds the retry loop. An unbounded loop during a long Anthropic
        outage would burn the cron's timeout budget and never surface the
        failure.
        """
        error_result = _make_result(returncode=1, stderr="API Error: 529 Overloaded.")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.time.sleep"):
                with patch(
                    "src.claude_runner.subprocess.run",
                    return_value=error_result,
                ) as mock_run:
                    with pytest.raises(RuntimeError, match="529"):
                        run_claude("prompt", "test")

        assert mock_run.call_count == 3

    def test_non_transient_error_does_not_retry(self):
        """Verifies: a non-5xx error (e.g. auth failure) fails immediately
        with one subprocess call and zero sleeps.
        Why: retrying deterministic errors (bad credentials, invalid prompt)
        wastes time and can amplify the problem (e.g. account lockout). Only
        transient server-side errors should be retried.
        """
        error_result = _make_result(returncode=1, stderr="auth error")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.time.sleep") as mock_sleep:
                with patch(
                    "src.claude_runner.subprocess.run",
                    return_value=error_result,
                ) as mock_run:
                    with pytest.raises(RuntimeError, match="auth error"):
                        run_claude("prompt", "test")

        assert mock_run.call_count == 1
        assert mock_sleep.call_count == 0

    def test_success_first_attempt_does_not_sleep(self):
        """Verifies: a successful first attempt completes without any
        time.sleep call.
        Why: guards against accidentally introducing an unconditional pre- or
        post-call delay during refactoring. The happy path must remain fast.
        """
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.time.sleep") as mock_sleep:
                with patch("src.claude_runner.subprocess.run", return_value=_make_result(stdout="ok")):
                    run_claude("prompt", "test")
        assert mock_sleep.call_count == 0

    def test_exponential_backoff_increases(self):
        """Verifies: between three attempts, two sleeps occur and the second
        sleep duration is strictly greater than the first.
        Why: exponential (not constant) backoff is what gives the upstream
        service room to recover. A regression to fixed delay would hammer the
        API and likely extend the outage from the client's perspective.
        """
        error_result = _make_result(returncode=1, stderr="API Error: 529 Overloaded.")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.time.sleep") as mock_sleep:
                with patch("src.claude_runner.subprocess.run", return_value=error_result):
                    with pytest.raises(RuntimeError):
                        run_claude("prompt", "test")

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert len(delays) == 2
        assert delays[1] > delays[0]

    def test_max_attempts_param_overrides_default(self):
        """Verifies: passing max_attempts=2 caps subprocess calls at 2 even
        when every attempt would be retryable.
        Why: makes the policy injectable for callers (and for these tests) so
        the retry budget can be tuned per-job without changing global
        constants.
        """
        error_result = _make_result(returncode=1, stderr="API Error: 529 Overloaded.")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.time.sleep"):
                with patch(
                    "src.claude_runner.subprocess.run",
                    return_value=error_result,
                ) as mock_run:
                    with pytest.raises(RuntimeError):
                        run_claude("prompt", "test", max_attempts=2)

        assert mock_run.call_count == 2

    def test_invalid_max_attempts_raises_value_error(self):
        """Verifies: max_attempts <= 0 raises ValueError before any subprocess
        call is made.
        Why: with the previous loop-only logic, a caller passing
        max_attempts=0 would skip the loop entirely and surface a misleading
        "rc=0" error. Fail loudly at the boundary instead.
        """
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run") as mock_run:
                with pytest.raises(ValueError, match="max_attempts"):
                    run_claude("prompt", "test", max_attempts=0)
                with pytest.raises(ValueError, match="max_attempts"):
                    run_claude("prompt", "test", max_attempts=-1)
        assert mock_run.call_count == 0

    def test_timeout_not_retried(self):
        """Verifies: subprocess.TimeoutExpired raises RuntimeError after a
        single subprocess call, with no retry attempts.
        Why: a timeout already consumed the full timeout budget; retrying
        would multiply wall-clock cost (e.g. 3 x 300s = 15 min) and a hung
        CLI likely won't recover on its own. Fail fast and let the operator
        diagnose.
        """
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "src.claude_runner.subprocess.run",
                side_effect=subprocess.TimeoutExpired("claude", 300),
            ) as mock_run:
                with pytest.raises(RuntimeError, match="タイムアウト"):
                    run_claude("prompt", "test", timeout=300)

        assert mock_run.call_count == 1


class TestBuildEnv:
    def test_cli_mode_strips_anthropic_api_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "should-be-removed")
        env = claude_runner.build_env(auth_mode="cli")
        assert "ANTHROPIC_API_KEY" not in env

    def test_cli_mode_preserves_other_env(self, monkeypatch):
        monkeypatch.setenv("PATH", "/usr/local/bin")
        monkeypatch.setenv("OTHER_VAR", "kept")
        env = claude_runner.build_env(auth_mode="cli")
        assert env.get("OTHER_VAR") == "kept"
        assert "/usr/local/bin" in env.get("PATH", "")

    def test_api_mode_injects_keychain_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        store = {("ai-agent", "ANTHROPIC_API_KEY"): "key-xyz"}

        class _Fake:
            def get_password(self, service, name):
                return store.get((service, name))

            def set_password(self, service, name, value):
                store[(service, name)] = value

            def delete_password(self, service, name):
                store.pop((service, name), None)

        monkeypatch.setattr(credentials, "_backend", _Fake())

        env = claude_runner.build_env(auth_mode="api")
        assert env.get("ANTHROPIC_API_KEY") == "key-xyz"

    def test_api_mode_falls_back_to_env_when_keychain_empty(self, monkeypatch):
        """If auth_mode=api but Keychain has no key, the .env value (loaded into
        os.environ by the wrapper script) is used instead — same precedence as
        credentials.get_credential.
        """
        monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")

        class _Empty:
            def get_password(self, service, name):
                return None

            def set_password(self, service, name, value):
                pass

            def delete_password(self, service, name):
                pass

        monkeypatch.setattr(credentials, "_backend", _Empty())

        env = claude_runner.build_env(auth_mode="api")
        assert env.get("ANTHROPIC_API_KEY") == "from-env"

    def test_api_mode_does_not_inject_when_no_key_available(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        class _Empty:
            def get_password(self, service, name):
                return None

            def set_password(self, service, name, value):
                pass

            def delete_password(self, service, name):
                pass

        monkeypatch.setattr(credentials, "_backend", _Empty())

        env = claude_runner.build_env(auth_mode="api")
        assert "ANTHROPIC_API_KEY" not in env


class TestRunClaudeAuthMode:
    def test_run_claude_in_api_mode_injects_keychain_key(self, monkeypatch):
        """When state.auth_mode=api, run_claude's subprocess env contains the
        Keychain-stored ANTHROPIC_API_KEY."""
        state_mod.write_state(state_mod.State(auth_mode="api"))

        store = {("ai-agent", "ANTHROPIC_API_KEY"): "from-keychain"}

        class _Fake:
            def get_password(self, service, name):
                return store.get((service, name))

            def set_password(self, service, name, value):
                store[(service, name)] = value

            def delete_password(self, service, name):
                store.pop((service, name), None)

        monkeypatch.setattr(credentials, "_backend", _Fake())
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        captured = {}

        def fake_run(args, **kwargs):
            captured["env"] = kwargs.get("env", {})
            return _make_result()

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run", side_effect=fake_run):
                run_claude("prompt", "test")

        assert captured["env"].get("ANTHROPIC_API_KEY") == "from-keychain"

    def test_run_claude_in_cli_mode_strips_api_key_even_if_keychain_has_one(
        self, monkeypatch
    ):
        """When state.auth_mode=cli, the Keychain key must NOT leak into the
        subprocess env — claude CLI should use its own OAuth session instead.
        Symmetric to the api-mode injection test."""
        state_mod.write_state(state_mod.State(auth_mode="cli"))

        store = {("ai-agent", "ANTHROPIC_API_KEY"): "from-keychain"}

        class _Fake:
            def get_password(self, service, name):
                return store.get((service, name))

            def set_password(self, service, name, value):
                store[(service, name)] = value

            def delete_password(self, service, name):
                store.pop((service, name), None)

        monkeypatch.setattr(credentials, "_backend", _Fake())
        monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env-also-present")

        captured = {}

        def fake_run(args, **kwargs):
            captured["env"] = kwargs.get("env", {})
            return _make_result()

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.run", side_effect=fake_run):
                run_claude("prompt", "test")

        assert "ANTHROPIC_API_KEY" not in captured["env"]
