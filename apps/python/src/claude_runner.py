import json
import os
import shutil
import subprocess
import time
from datetime import datetime

from src import config as config_mod
from src import credentials as cred_mod
from src import state as state_mod
from src.constants import (
    DEFAULT_MODEL,
    PARTIAL_OUTPUT_DIR,
    RETRY_BACKOFF_FACTOR,
    RETRY_BASE_DELAY,
    RETRY_MAX_ATTEMPTS,
)
from src.logger import get_logger
from src.notifier.local_md import write_md_file
from src.transient_errors import is_transient
from src.usage_logger import log_usage_from_result

logger = get_logger(__name__)


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
    timeout: int = 300,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
) -> str:
    """Invoke the claude CLI as a subprocess and return the result.

    By not passing ANTHROPIC_API_KEY to the child process, WebSearch uses
    subscription auth (OAuth).

    Anthropic API 5xx errors (e.g. 529 Overloaded) are retried with exponential
    backoff up to ``max_attempts`` times.
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
        "--output-format", "json",
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
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                env=env,
            )
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


