import json
import os
import shutil
import subprocess
import time

from src import config as config_mod
from src import credentials as cred_mod
from src import state as state_mod
from src.constants import (
    DEFAULT_MODEL,
    RETRY_BACKOFF_FACTOR,
    RETRY_BASE_DELAY,
    RETRY_MAX_ATTEMPTS,
)
from src.logger import get_logger
from src.transient_errors import is_transient
from src.usage_logger import log_usage

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

    usage = parsed.get("usage")
    if isinstance(usage, dict):
        log_usage(
            label=label,
            usage=usage,
            cost_usd=parsed.get("total_cost_usd"),
            duration_ms=parsed.get("duration_ms"),
        )
    else:
        # Calls without usage can happen in normal operation, so keep this at debug (avoid noise).
        logger.debug("no usage in claude CLI output, skipping usage log [%s]", label)

    return result_text.strip() if isinstance(result_text, str) else str(result_text)


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
    ]

    last_returncode = 0
    last_detail = ""
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

        if is_transient(result.stdout, result.stderr) and attempt < max_attempts:
            delay = _backoff_delay(attempt)
            logger.warning(
                "transient error detected, retrying in %.1fs [%s] (attempt %d/%d)",
                delay, label, attempt, max_attempts,
            )
            time.sleep(delay)
            continue
        break

    if len(last_detail) > 2000:
        last_detail = last_detail[:2000] + "…(truncated)"
    raise RuntimeError(f"claude CLI error [{label}] rc={last_returncode}: {last_detail}")
