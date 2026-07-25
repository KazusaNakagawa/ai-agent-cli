import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from src import config as config_mod
from src import credentials as cred_mod
from src import state as state_mod
from src.claude_stream import StreamState, consume_stream_line
from src.constants import (
    DEFAULT_MODEL,
    PARTIAL_OUTPUT_DIR,
    RETRY_BACKOFF_FACTOR,
    RETRY_BASE_DELAY,
    RETRY_MAX_ATTEMPTS,
    TIMEOUT_CLAUDE_DEFAULT,
)
from src.logger import get_logger
from src.notifier.local_md import write_md_file
from src.transient_errors import is_transient
from src.usage_logger import log_usage_from_result

logger = get_logger(__name__)


# How long to wait for the reader threads to finish after the child exits or is
# killed. They are draining closed pipes at that point, so this only bounds a
# pathological case rather than a normal wait.
_READER_JOIN_TIMEOUT_SEC = 5

# The count is always logged in full; only the quoted messages are capped, so a
# storm of identical 529s can't produce a multi-kilobyte log line.
_API_ERRORS_LOGGED_MAX = 5


@dataclass
class _StreamResult:
    """Outcome of one streamed claude CLI call.

    Deliberately mirrors the ``subprocess.run`` CompletedProcess attributes
    run_claude already branches on, so retry / usage / error handling did not
    have to change when the transport switched to a stream.
    ``stdout`` is the terminal ``result`` record verbatim — not the whole
    stream — which keeps ``is_transient`` looking at the same haystack as
    before rather than at every intermediate tool result.
    """

    returncode: int
    stdout: str
    stderr: str


def _stream_claude(cmd: list[str], env: dict[str, str], timeout: int, label: str) -> _StreamResult:
    """Run the claude CLI, parsing ``stream-json`` output as it arrives.

    Streaming exists for the failure path: under ``--output-format json`` the
    CLI prints nothing until it finishes, so a call killed at its timeout left
    no trace of work it had already done (#421 — two briefing runs on
    2026-07-26 each discarded minutes of billed output). Here the text produced
    so far rides out on ``TimeoutExpired.output``, which the caller already
    feeds to ``_save_partial_output``.

    Raises ``subprocess.TimeoutExpired`` — same contract as ``subprocess.run``.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=env,
    )
    state = StreamState()
    text_lines: list[str] = []
    stderr_chunks: list[bytes] = []

    # Each reader closes the pipe it owns. Closing from the main thread instead
    # could pull the file object out from under a blocked read; leaving them to
    # garbage collection leaks descriptors in the long-lived web process, which
    # calls this on every briefing/chat run.
    def _read_stdout() -> None:
        try:
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line:
                    text_lines.extend(consume_stream_line(line, state))
        finally:
            proc.stdout.close()

    def _read_stderr() -> None:
        # Drained concurrently: a large stderr write would otherwise fill the
        # OS pipe buffer and block the child mid-run.
        try:
            for chunk in iter(lambda: proc.stderr.read(4096), b""):
                stderr_chunks.append(chunk)
        finally:
            proc.stderr.close()

    readers = [
        threading.Thread(target=_read_stdout, daemon=True),
        threading.Thread(target=_read_stderr, daemon=True),
    ]
    for reader in readers:
        reader.start()

    def _finish_readers() -> None:
        for reader in readers:
            reader.join(timeout=_READER_JOIN_TIMEOUT_SEC)

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        _finish_readers()
        _log_api_errors(state, label)
        raise subprocess.TimeoutExpired(
            cmd, timeout, output=_collected_text(text_lines, state),
        ) from None

    _finish_readers()
    _log_api_errors(state, label)
    return _StreamResult(
        returncode=proc.returncode,
        stdout=state.result_raw or "",
        stderr=b"".join(stderr_chunks).decode("utf-8", errors="replace"),
    )


def _collected_text(text_lines: list[str], state: StreamState) -> str:
    """Join the streamed assistant text, including the unterminated last line."""
    parts = list(text_lines)
    if state.text_buf:
        parts.append(state.text_buf)
    return "\n".join(parts)


def _log_api_errors(state: StreamState, label: str) -> None:
    """Surface upstream API errors that the process exit code hides.

    The WebSearch server tool answers an overload with an "API Error: 529"
    tool result and the model just retries the query, so the run still exits 0
    while burning minutes. Without this the only record is the claude CLI's own
    session transcript.
    """
    if not state.api_errors:
        return
    shown = state.api_errors[:_API_ERRORS_LOGGED_MAX]
    suffix = "" if len(state.api_errors) <= _API_ERRORS_LOGGED_MAX else " …"
    logger.warning(
        "%d in-session API error(s) during [%s] — the model retried these, "
        "which inflates wall-clock time: %s%s",
        len(state.api_errors), label, "; ".join(shown), suffix,
    )


def _parse_and_log_usage(stdout: str, label: str) -> str:
    """Parse ``--output-format json`` stdout, record usage, and return the text result.

    If the output is not JSON or lacks a ``result`` field, log a warning and
    return the raw stdout as-is (skipping the usage log) — usage measurement must
    not break the main task.
    """
    try:
        parsed = json.loads(stdout)
        result_text = parsed["result"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning(
            "could not parse claude CLI output as JSON, skipping usage log [%s]", label,
        )
        return stdout.strip()

    if not log_usage_from_result(label, parsed):
        # Calls without usage can happen in normal operation, so keep this at debug (avoid noise).
        logger.debug("no usage in claude CLI output, skipping usage log [%s]", label)

    return result_text.strip() if isinstance(result_text, str) else str(result_text)


def _extract_partial_text(raw_output: str | None) -> str | None:
    """Best-effort salvage of usable text from a failed claude CLI call.

    Handles both a JSON payload with ``is_error: true`` (the CLI still emits
    a ``result`` field in that case) and a process killed before it could
    print valid JSON at all (fall back to the raw output).
    """
    if not raw_output or not raw_output.strip():
        return None
    try:
        parsed = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        return raw_output.strip()
    result_text = parsed.get("result") if isinstance(parsed, dict) else None
    if isinstance(result_text, str) and result_text.strip():
        return result_text.strip()
    return None


def _save_partial_output(label: str, raw_output: str | None) -> None:
    """Persist whatever partial text is salvageable so a failed run doesn't
    silently lose work the model already produced. Best-effort: a failure to
    save must not mask the caller's original error.
    """
    text = _extract_partial_text(raw_output)
    if text is None:
        return
    safe_label = label.replace("/", "_").strip() or "unknown"
    filename = f"{safe_label}_{datetime.now():%Y%m%d-%H%M%S}.md"
    try:
        path = write_md_file(PARTIAL_OUTPUT_DIR, filename, text)
        logger.warning("saved partial output before failing [%s]: %s", label, path)
    except OSError:
        logger.warning("failed to save partial output [%s]", label, exc_info=True)


def _config_model() -> str | None:
    """Return the ``model`` field from briefing.json. None if it cannot be read.

    To avoid blocking model resolution when briefing.json is missing or broken,
    swallow exceptions and return None (the caller falls back to DEFAULT_MODEL).
    """
    try:
        model = config_mod.CONFIG.model
    except FileNotFoundError:
        # briefing.json not yet created (e.g. right after web startup) is expected; ignore quietly.
        return None
    except Exception:  # noqa: BLE001 — unexpected config errors must not block model resolution
        logger.warning("failed to read model from config, using DEFAULT_MODEL", exc_info=True)
        return None
    return model.strip() if model and model.strip() else None


def get_model() -> str:
    """Resolve the model ID passed to the claude CLI.

    Precedence: ``CLAUDE_MODEL`` env > briefing.json ``model`` > ``DEFAULT_MODEL``.
    env stays highest priority for ad-hoc overrides.
    """
    env_model = os.environ.get("CLAUDE_MODEL", "").strip()
    if env_model:
        return env_model
    return _config_model() or DEFAULT_MODEL


def _backoff_delay(attempt: int) -> float:
    """Return the seconds to wait before the ``attempt``-th retry (1-indexed)."""
    return RETRY_BASE_DELAY * (RETRY_BACKOFF_FACTOR ** (attempt - 1))


def build_env(auth_mode: str) -> dict[str, str]:
    """Build the env passed to the subprocess according to auth_mode.

    - ``cli``: strip ``ANTHROPIC_API_KEY`` so the Claude Code CLI uses its OAuth.
    - ``api``: pull ``ANTHROPIC_API_KEY`` from the Keychain (or os.environ via
      .env) and inject it into env. If it is in neither, the key stays unset —
      the claude CLI then raises an auth error on the caller's side.

    Public API — also imported by ``web.routers.chat``. (The earlier underscore
    prefix was a stale "internal" signal that didn't reflect actual usage.)
    """
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    if auth_mode == "api":
        key = cred_mod.get_credential("ANTHROPIC_API_KEY")
        if key:
            env["ANTHROPIC_API_KEY"] = key
    return env


def run_claude(
    prompt: str,
    label: str,
    timeout: int = TIMEOUT_CLAUDE_DEFAULT,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
) -> str:
    """Invoke the claude CLI as a subprocess and return the result.

    By not passing ANTHROPIC_API_KEY to the child process, WebSearch uses
    subscription auth (OAuth).

    Anthropic API 5xx errors (e.g. 529 Overloaded) are retried with exponential
    backoff up to ``max_attempts`` times.

    ``timeout`` defaults to ``TIMEOUT_CLAUDE_DEFAULT`` (900s), sized for the long
    tail of WebSearch-heavy prompts rather than for interactive latency: a
    timeout kills the subprocess and throws away everything it has produced, and
    ``--output-format json`` emits nothing until the very end, so a budget set
    too tight discards minutes of billed work. Callers on a synchronous or
    user-facing path should pass a shorter explicit ``timeout`` — every current
    consumer is an offline batch job (briefing, weekly recap, evaluator, wordset,
    self-agent profile, XSS intel).
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1 (got {max_attempts})")

    claude_path = shutil.which("claude")
    if claude_path is None:
        raise RuntimeError("claude CLI not found. Check your PATH.")

    env = build_env(auth_mode=state_mod.read_state().auth_mode)
    model = get_model()
    cmd = [
        claude_path, "-p", prompt,
        # stream-json (rather than json) so text is readable before the call
        # ends — that is what makes a timed-out run salvageable (#421).
        # --verbose is required by the CLI for stream-json under -p, and
        # --include-partial-messages is what emits the incremental deltas.
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--allowedTools", "WebSearch",
        "--model", model,
        # Project-level settings.local.json can pre-approve Skill(*) and MCP
        # tools that take effect regardless of --allowedTools above, letting
        # an unrelated skill self-fire mid-run and hijack the returned text
        # (#409). These two flags close that gap independent of local settings.
        "--disable-slash-commands",
        "--strict-mcp-config",
    ]

    last_returncode = 0
    last_detail = ""
    last_stdout = ""
    for attempt in range(1, max_attempts + 1):
        logger.info(
            "claude CLI call start: %s (timeout=%ds, attempt=%d/%d)",
            label, timeout, attempt, max_attempts,
        )
        try:
            result = _stream_claude(cmd, env, timeout, label)
        except subprocess.TimeoutExpired as exc:
            logger.error("claude CLI timeout: %s (%ds)", label, timeout)
            _save_partial_output(label, exc.stdout)
            raise RuntimeError(f"claude CLI timed out ({label})") from exc

        if result.returncode == 0:
            logger.info("claude CLI done: %s (%d chars)", label, len(result.stdout))
            return _parse_and_log_usage(result.stdout, label)

        logger.error(
            "claude CLI error [%s] rc=%d attempt=%d/%d\nstdout=%s\nstderr=%s",
            label, result.returncode, attempt, max_attempts, result.stdout, result.stderr,
        )
        last_returncode = result.returncode
        last_detail = (result.stderr or result.stdout or "").strip()
        last_stdout = result.stdout

        if is_transient(result.stdout, result.stderr) and attempt < max_attempts:
            delay = _backoff_delay(attempt)
            logger.warning(
                "transient error detected, retrying in %.1fs [%s] (attempt %d/%d)",
                delay, label, attempt, max_attempts,
            )
            time.sleep(delay)
            continue
        break

    _save_partial_output(label, last_stdout)
    if len(last_detail) > 2000:
        last_detail = last_detail[:2000] + "…(truncated)"
    raise RuntimeError(f"claude CLI error [{label}] rc={last_returncode}: {last_detail}")


