import os
import re
import shutil
import subprocess
import time

from src import credentials as cred_mod
from src import state as state_mod
from src.constants import (
    DEFAULT_MODEL,
    RETRY_BACKOFF_FACTOR,
    RETRY_BASE_DELAY,
    RETRY_MAX_ATTEMPTS,
)
from src.logger import get_logger

logger = get_logger(__name__)

# Anthropic API の 5xx 系一時障害 (例: "API Error: 529 Overloaded.") を検出
_TRANSIENT_ERROR_RE = re.compile(r"API Error:\s*5\d\d")


def get_model() -> str:
    """環境変数 CLAUDE_MODEL を読み、空・空白の場合はデフォルトを返す。"""
    env_model = os.environ.get("CLAUDE_MODEL", "").strip()
    return env_model if env_model else DEFAULT_MODEL


def _is_transient_error(stdout: str, stderr: str) -> bool:
    """stdout/stderr に Anthropic API の 5xx エラー表記が含まれるか判定する。"""
    return bool(_TRANSIENT_ERROR_RE.search((stdout or "") + "\n" + (stderr or "")))


def _backoff_delay(attempt: int) -> float:
    """attempt 番目 (1-indexed) のリトライ前に待機する秒数を返す。"""
    return RETRY_BASE_DELAY * (RETRY_BACKOFF_FACTOR ** (attempt - 1))


def _build_env(auth_mode: str) -> dict[str, str]:
    """auth_mode に応じてサブプロセスに渡す env を作る。

    - ``cli``: ``ANTHROPIC_API_KEY`` を削除して Claude Code CLI の OAuth を使わせる。
    - ``api``: Keychain (なければ .env 経由の os.environ) から
      ``ANTHROPIC_API_KEY`` を取り出して env に注入する。Keychain にも env にも
      無ければキーは未設定のまま — 呼び出し側で claude CLI が認証エラーになる。
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
    """claude CLI を subprocess で呼び出し、結果を返す。

    ANTHROPIC_API_KEY を子プロセスに渡さないことで、
    WebSearch がサブスクリプション認証(OAuth)を使うようにする。

    Anthropic API の 5xx 系エラー (例: 529 Overloaded) は指数バックオフで
    最大 ``max_attempts`` 回までリトライする。
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts は 1 以上である必要があります (got {max_attempts})")

    claude_path = shutil.which("claude")
    if claude_path is None:
        raise RuntimeError("claude CLI が見つかりません。PATH を確認してください。")

    env = _build_env(auth_mode=state_mod.read_state().auth_mode)
    model = get_model()
    cmd = [claude_path, "-p", prompt, "--allowedTools", "WebSearch", "--model", model]

    last_returncode = 0
    last_detail = ""
    for attempt in range(1, max_attempts + 1):
        logger.info(
            "claude CLI 呼び出し開始: %s (timeout=%ds, attempt=%d/%d)",
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
            logger.error("claude CLI タイムアウト: %s (%ds)", label, timeout)
            raise RuntimeError(f"claude CLI がタイムアウトしました ({label})") from exc

        if result.returncode == 0:
            logger.info("claude CLI 完了: %s (%d文字)", label, len(result.stdout))
            return result.stdout.strip()

        logger.error(
            "claude CLI エラー [%s] rc=%d attempt=%d/%d\nstdout=%s\nstderr=%s",
            label, result.returncode, attempt, max_attempts, result.stdout, result.stderr,
        )
        last_returncode = result.returncode
        last_detail = (result.stderr or result.stdout or "").strip()

        if _is_transient_error(result.stdout, result.stderr) and attempt < max_attempts:
            delay = _backoff_delay(attempt)
            logger.warning(
                "一時的なエラーを検出、%.1fs 後にリトライします [%s] (attempt %d/%d)",
                delay, label, attempt, max_attempts,
            )
            time.sleep(delay)
            continue
        break

    if len(last_detail) > 2000:
        last_detail = last_detail[:2000] + "…(truncated)"
    raise RuntimeError(f"claude CLI エラー [{label}] rc={last_returncode}: {last_detail}")
