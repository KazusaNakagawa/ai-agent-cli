import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src import claude_runner, credentials, state as state_mod
from src.claude_runner import run_claude
from src.constants import DEFAULT_MODEL


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
            with pytest.raises(RuntimeError, match="claude CLI not found"):
                run_claude("prompt", "test")

    def test_success_returns_stripped_stdout(self):
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", return_value=_make_result(stdout="  hello  \n")):
                result = run_claude("prompt", "test")
        assert result == "hello"

    def test_timeout_raises_runtime_error(self):
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "src.claude_runner._stream_claude",
                side_effect=subprocess.TimeoutExpired("claude", 300),
            ):
                with pytest.raises(RuntimeError, match="timed out"):
                    run_claude("prompt", "test", timeout=300)

    def test_nonzero_returncode_raises_with_stderr(self):
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "src.claude_runner._stream_claude",
                return_value=_make_result(returncode=1, stdout="", stderr="auth error"),
            ):
                with pytest.raises(RuntimeError, match="auth error"):
                    run_claude("prompt", "test")

    def test_nonzero_returncode_falls_back_to_stdout(self):
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "src.claude_runner._stream_claude",
                return_value=_make_result(returncode=1, stdout="stdout error", stderr=""),
            ):
                with pytest.raises(RuntimeError, match="stdout error"):
                    run_claude("prompt", "test")

    def test_long_error_is_truncated(self):
        long_stderr = "x" * 3000
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "src.claude_runner._stream_claude",
                return_value=_make_result(returncode=1, stdout="", stderr=long_stderr),
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    run_claude("prompt", "test")
        assert "truncated" in str(exc_info.value)

    def test_api_key_excluded_from_subprocess_env(self):
        captured = {}

        def fake_run(cmd, env, timeout, label):
            captured["env"] = env
            return _make_result()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret-key"}):
            with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
                with patch("src.claude_runner._stream_claude", side_effect=fake_run):
                    run_claude("prompt", "test")

        assert "ANTHROPIC_API_KEY" not in captured["env"]

    def test_stdin_is_devnull(self):
        """The child must never inherit a terminal: a claude CLI that blocks on
        stdin would hang a batch run until its timeout."""
        captured = {}

        class _Proc:
            stdout = __import__("io").BytesIO(b"")
            stderr = __import__("io").BytesIO(b"")
            returncode = 0

            def wait(self, timeout=None):
                return 0

        def fake_popen(cmd, **kwargs):
            captured["stdin"] = kwargs.get("stdin")
            return _Proc()

        with patch("src.claude_runner.subprocess.Popen", side_effect=fake_popen):
            claude_runner._stream_claude(["claude"], {}, 300, "test")

        assert captured["stdin"] == subprocess.DEVNULL

    def test_cmd_disables_skills_and_strict_mcp(self):
        """Verifies: the claude CLI subprocess command disables skill
        auto-fire and any MCP server not explicitly allow-listed.
        Why: project-level settings.local.json can pre-approve Skill(*) and
        MCP tools, which takes effect regardless of the narrower
        --allowedTools passed to this call. That let the notion-import skill
        self-fire mid-batch-run and return its own short completion report
        instead of the generated briefing, silently overwriting the local MD
        file with junk (#409). --disable-slash-commands and
        --strict-mcp-config close that gap independent of local settings.
        """
        captured = {}

        def fake_run(cmd, env, timeout, label):
            captured["cmd"] = cmd
            return _make_result()

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", side_effect=fake_run):
                run_claude("prompt", "test")

        assert "--disable-slash-commands" in captured["cmd"]
        assert "--strict-mcp-config" in captured["cmd"]


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
            with patch("src.claude_runner._stream_claude", return_value=_make_result(stdout=payload)):
                with patch("src.usage_logger.log_usage") as mock_log:
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
            with patch("src.claude_runner._stream_claude", return_value=_make_result(stdout="  plain text  ")):
                with patch("src.usage_logger.log_usage") as mock_log:
                    result = run_claude("prompt", "test")

        assert result == "plain text"
        mock_log.assert_not_called()

    def test_json_without_usage_returns_result_and_skips_logging(self):
        payload = json.dumps({"result": "ok"})
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", return_value=_make_result(stdout=payload)):
                with patch("src.usage_logger.log_usage") as mock_log:
                    result = run_claude("prompt", "test")

        assert result == "ok"
        mock_log.assert_not_called()

    def test_json_without_result_field_falls_back_to_stdout(self):
        """result フィールドの無い JSON は raw stdout にフォールバックし、使用量も記録しない。"""
        payload = json.dumps({"foo": 1})
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", return_value=_make_result(stdout=payload)):
                with patch("src.usage_logger.log_usage") as mock_log:
                    result = run_claude("prompt", "test")

        assert result == payload
        mock_log.assert_not_called()

    def test_non_string_result_is_stringified_and_usage_logged(self):
        """result が文字列以外でも str() 化して返し、usage は記録する。"""
        payload = json.dumps({"result": ["x", "y"], "usage": {"input_tokens": 5, "output_tokens": 6}})
        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", return_value=_make_result(stdout=payload)):
                with patch("src.usage_logger.log_usage") as mock_log:
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
                    "src.claude_runner._stream_claude",
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
                    "src.claude_runner._stream_claude",
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
                    "src.claude_runner._stream_claude",
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
                    "src.claude_runner._stream_claude",
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
                    "src.claude_runner._stream_claude",
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
                with patch("src.claude_runner._stream_claude", return_value=_make_result(stdout="ok")):
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
                with patch("src.claude_runner._stream_claude", return_value=error_result):
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
                    "src.claude_runner._stream_claude",
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
            with patch("src.claude_runner._stream_claude") as mock_run:
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
                "src.claude_runner._stream_claude",
                side_effect=subprocess.TimeoutExpired("claude", 300),
            ) as mock_run:
                with pytest.raises(RuntimeError, match="timed out"):
                    run_claude("prompt", "test", timeout=300)

        assert mock_run.call_count == 1


class TestRunClaudePartialOutput:
    def test_saves_partial_result_when_retries_exhausted(self, monkeypatch, tmp_path):
        """Verifies: when every attempt fails with a transient error but the
        CLI's stdout still carries a `result` field (is_error=true), the
        salvaged text is written under PARTIAL_OUTPUT_DIR before RuntimeError
        raises.
        Why: a run that burns the full retry budget and still fails currently
        discards whatever text the model already produced (#406).
        """
        monkeypatch.setattr(claude_runner, "PARTIAL_OUTPUT_DIR", tmp_path)
        payload = json.dumps({"is_error": True, "result": "partial analysis text"})
        error_result = _make_result(returncode=1, stdout=payload, stderr="API Error: 529 Overloaded.")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.time.sleep"):
                with patch("src.claude_runner._stream_claude", return_value=error_result):
                    with pytest.raises(RuntimeError):
                        run_claude("prompt", "test-label", max_attempts=2)

        saved = list(tmp_path.glob("test-label_*.md"))
        assert len(saved) == 1
        assert saved[0].read_text(encoding="utf-8") == "partial analysis text"

    def test_no_file_written_when_nothing_salvageable(self, monkeypatch, tmp_path):
        """Verifies: a plain non-transient failure with no usable result text
        (no JSON, no partial output) writes nothing to PARTIAL_OUTPUT_DIR.
        """
        monkeypatch.setattr(claude_runner, "PARTIAL_OUTPUT_DIR", tmp_path)
        error_result = _make_result(returncode=1, stdout="", stderr="auth error")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", return_value=error_result):
                with pytest.raises(RuntimeError):
                    run_claude("prompt", "test-label")

        assert list(tmp_path.iterdir()) == []

    def test_saves_partial_output_on_timeout(self, monkeypatch, tmp_path):
        """Verifies: a TimeoutExpired carrying partially-captured stdout still
        salvages the text instead of discarding it silently.
        """
        monkeypatch.setattr(claude_runner, "PARTIAL_OUTPUT_DIR", tmp_path)
        exc = subprocess.TimeoutExpired("claude", 300, output="partial before kill")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", side_effect=exc):
                with pytest.raises(RuntimeError, match="timed out"):
                    run_claude("prompt", "test-label", timeout=300)

        saved = list(tmp_path.glob("test-label_*.md"))
        assert len(saved) == 1
        assert saved[0].read_text(encoding="utf-8") == "partial before kill"

    def test_timeout_with_no_captured_output_saves_nothing(self, monkeypatch, tmp_path):
        """Verifies: a TimeoutExpired with no captured stdout (the common case,
        since --output-format json only prints once at completion) writes no
        file rather than an empty one.
        """
        monkeypatch.setattr(claude_runner, "PARTIAL_OUTPUT_DIR", tmp_path)
        exc = subprocess.TimeoutExpired("claude", 300)

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", side_effect=exc):
                with pytest.raises(RuntimeError, match="timed out"):
                    run_claude("prompt", "test-label", timeout=300)

        assert list(tmp_path.iterdir()) == []

    def test_partial_save_failure_does_not_mask_original_error(self, monkeypatch, tmp_path):
        """Verifies: if persisting the partial artifact itself fails (e.g. the
        target path is unwritable), run_claude still raises the original
        RuntimeError rather than an unrelated file-write error.
        """
        blocked = tmp_path / "not_a_dir"
        blocked.write_text("x")  # a file, not a directory -> mkdir(parents=True) fails
        monkeypatch.setattr(claude_runner, "PARTIAL_OUTPUT_DIR", blocked / "sub")
        error_result = _make_result(returncode=1, stdout=json.dumps({"result": "text"}), stderr="auth error")

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", return_value=error_result):
                with pytest.raises(RuntimeError, match="auth error"):
                    run_claude("prompt", "test-label")


class TestGetModel:
    def test_env_var_takes_precedence_over_config(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_MODEL", "env-model")
        monkeypatch.setattr(claude_runner, "_config_model", lambda: "config-model")
        assert claude_runner.get_model() == "env-model"

    def test_config_model_used_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_MODEL", raising=False)
        monkeypatch.setattr(claude_runner, "_config_model", lambda: "config-model")
        assert claude_runner.get_model() == "config-model"

    def test_falls_back_to_default_when_neither_set(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_MODEL", raising=False)
        monkeypatch.setattr(claude_runner, "_config_model", lambda: None)
        assert claude_runner.get_model() == DEFAULT_MODEL

    def test_blank_env_var_is_ignored(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_MODEL", "   ")
        monkeypatch.setattr(claude_runner, "_config_model", lambda: None)
        assert claude_runner.get_model() == DEFAULT_MODEL

    def test_config_model_reads_config_field(self, monkeypatch):
        """briefing.json の model フィールドが解決に反映される。"""
        fake_config_mod = MagicMock()
        fake_config_mod.CONFIG.model = "claude-sonnet-4-6"
        monkeypatch.setattr(claude_runner, "config_mod", fake_config_mod)
        assert claude_runner._config_model() == "claude-sonnet-4-6"

    def test_config_model_returns_none_when_missing_file(self, monkeypatch):
        """briefing.json 未作成 (FileNotFoundError) は静かに None を返す。"""
        class _Missing:
            @property
            def CONFIG(self):
                raise FileNotFoundError("no briefing.json")

        monkeypatch.setattr(claude_runner, "config_mod", _Missing())
        with patch.object(claude_runner.logger, "warning") as mock_warn:
            assert claude_runner._config_model() is None
        mock_warn.assert_not_called()  # 想定内なので警告は出さない

    def test_config_model_logs_and_returns_none_on_unexpected_error(self, monkeypatch):
        """想定外の config エラーは握りつぶしつつ警告ログを出して None を返す。"""
        class _Broken:
            @property
            def CONFIG(self):
                raise ValueError("broken config")

        monkeypatch.setattr(claude_runner, "config_mod", _Broken())
        with patch.object(claude_runner.logger, "warning") as mock_warn:
            assert claude_runner._config_model() is None
        mock_warn.assert_called_once()


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

        def fake_run(cmd, env, timeout, label):
            captured["env"] = env
            return _make_result()

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", side_effect=fake_run):
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

        def fake_run(cmd, env, timeout, label):
            captured["env"] = env
            return _make_result()

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", side_effect=fake_run):
                run_claude("prompt", "test")

        assert "ANTHROPIC_API_KEY" not in captured["env"]



class _FakeProc:
    """Minimal Popen stand-in for _stream_claude tests."""

    def __init__(self, stdout_lines, stderr=b"", returncode=0, hangs=False):
        import io
        self.stdout = io.BytesIO("\n".join(stdout_lines).encode("utf-8"))
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode
        self._hangs = hangs
        self.killed = False

    def wait(self, timeout=None):
        if self._hangs and timeout is not None:
            raise subprocess.TimeoutExpired("claude", timeout)
        return self.returncode

    def kill(self):
        self.killed = True
        self._hangs = False


def _delta_line(text):
    return json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}},
    })


def _result_line(result="final answer", **fields):
    return json.dumps({"type": "result", "subtype": "success", "result": result, **fields})


def _tool_error_line(msg):
    return json.dumps({
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": msg}]},
    })


class TestStreamClaude:
    def test_success_returns_terminal_result_record_as_stdout(self):
        """The terminal result line is handed back verbatim so the existing
        JSON parsing / usage-logging path keeps working unchanged."""
        line = _result_line(result="final answer", usage={"input_tokens": 1})
        proc = _FakeProc([_delta_line("intermediate chatter\n"), line])
        with patch("src.claude_runner.subprocess.Popen", return_value=proc):
            result = claude_runner._stream_claude(["claude"], {}, 300, "test")
        assert result.returncode == 0
        assert json.loads(result.stdout)["result"] == "final answer"

    def test_timeout_salvages_streamed_text_and_kills_process(self):
        """Failure case: the process never exits, so the text streamed so far
        must survive on the exception the caller already handles."""
        proc = _FakeProc([_delta_line("first line\nsecond line")], hangs=True)
        with patch("src.claude_runner.subprocess.Popen", return_value=proc):
            with pytest.raises(subprocess.TimeoutExpired) as exc:
                claude_runner._stream_claude(["claude"], {}, 300, "test")
        assert "first line" in exc.value.stdout
        assert "second line" in exc.value.stdout
        assert proc.killed is True

    def test_timeout_with_no_streamed_text_yields_empty_output(self):
        """Boundary: nothing streamed before the kill — no text to salvage."""
        proc = _FakeProc([], hangs=True)
        with patch("src.claude_runner.subprocess.Popen", return_value=proc):
            with pytest.raises(subprocess.TimeoutExpired) as exc:
                claude_runner._stream_claude(["claude"], {}, 300, "test")
        assert exc.value.stdout == ""

    def test_stderr_is_captured(self):
        proc = _FakeProc([_result_line()], stderr=b"warning: something")
        with patch("src.claude_runner.subprocess.Popen", return_value=proc):
            result = claude_runner._stream_claude(["claude"], {}, 300, "test")
        assert "warning: something" in result.stderr

    def test_in_session_api_errors_are_logged(self, caplog):
        """A 529 from the WebSearch server tool never fails the process, so it
        is only observable if the stream is inspected (#421)."""
        proc = _FakeProc([
            _tool_error_line("API Error: 529 Overloaded. This is a server-side issue"),
            _tool_error_line("API Error: 529 Overloaded. This is a server-side issue"),
            _result_line(),
        ])
        with caplog.at_level("WARNING"):
            with patch("src.claude_runner.subprocess.Popen", return_value=proc):
                claude_runner._stream_claude(["claude"], {}, 300, "メイン分析")
        assert "メイン分析" in caplog.text
        assert "529" in caplog.text

    def test_api_error_log_line_is_capped(self, caplog):
        """Boundary: a storm of identical 529s must not produce a multi-kilobyte
        log line — the full count is kept, the quoted messages are capped."""
        proc = _FakeProc(
            [_tool_error_line(f"API Error: 529 Overloaded #{i}") for i in range(20)]
            + [_result_line()]
        )
        with caplog.at_level("WARNING"):
            with patch("src.claude_runner.subprocess.Popen", return_value=proc):
                claude_runner._stream_claude(["claude"], {}, 300, "test")
        assert "20 in-session API error(s)" in caplog.text
        assert "#19" not in caplog.text

    def test_pipes_are_closed(self):
        """Descriptors must not be left to garbage collection: the web process
        is long-lived and calls this on every run."""
        proc = _FakeProc([_result_line()])
        with patch("src.claude_runner.subprocess.Popen", return_value=proc):
            claude_runner._stream_claude(["claude"], {}, 300, "test")
        assert proc.stdout.closed is True
        assert proc.stderr.closed is True

    def test_pipes_are_closed_on_timeout(self):
        proc = _FakeProc([_delta_line("partial")], hangs=True)
        with patch("src.claude_runner.subprocess.Popen", return_value=proc):
            with pytest.raises(subprocess.TimeoutExpired):
                claude_runner._stream_claude(["claude"], {}, 300, "test")
        assert proc.stdout.closed is True
        assert proc.stderr.closed is True

    def test_no_api_errors_logs_nothing(self):
        proc = _FakeProc([_result_line()])
        with patch("src.claude_runner.subprocess.Popen", return_value=proc):
            with patch("src.claude_runner.logger.warning") as warn:
                claude_runner._stream_claude(["claude"], {}, 300, "test")
        warn.assert_not_called()


class TestRunClaudeStreaming:
    def test_cmd_requests_streaming_output(self):
        """--include-partial-messages is what makes text available before the
        run finishes; without it a killed call still salvages nothing."""
        captured = {}

        def fake_stream(cmd, env, timeout, label):
            captured["cmd"] = cmd
            return _make_result(stdout=_result_line(result="ok"))

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner._stream_claude", side_effect=fake_stream):
                run_claude("prompt", "test")

        cmd = captured["cmd"]
        assert cmd[cmd.index("--output-format") + 1] == "stream-json"
        assert "--verbose" in cmd
        assert "--include-partial-messages" in cmd

    def test_timeout_writes_streamed_text_to_partial_output(self, monkeypatch, tmp_path):
        """End-to-end for #421: a timed-out call leaves the produced text on disk."""
        monkeypatch.setattr(claude_runner, "PARTIAL_OUTPUT_DIR", tmp_path)
        proc = _FakeProc([_delta_line("### 見出し\n本文です。")], hangs=True)

        with patch("src.claude_runner.shutil.which", return_value="/usr/bin/claude"):
            with patch("src.claude_runner.subprocess.Popen", return_value=proc):
                with pytest.raises(RuntimeError, match="timed out"):
                    run_claude("prompt", "メイン分析", timeout=300)

        files = list(tmp_path.glob("*.md"))
        assert len(files) == 1
        assert "### 見出し" in files[0].read_text(encoding="utf-8")
