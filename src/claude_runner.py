import os
import shutil
import subprocess
from src.logger import get_logger

logger = get_logger(__name__)


_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def get_model() -> str:
    """環境変数 CLAUDE_MODEL を読み、空・空白の場合はデフォルトを返す。"""
    env_model = os.environ.get("CLAUDE_MODEL", "").strip()
    return env_model if env_model else _DEFAULT_MODEL


def run_claude(prompt: str, label: str, timeout: int = 300) -> str:
    """claude CLI を subprocess で呼び出し、結果を返す。

    ANTHROPIC_API_KEY を子プロセスに渡さないことで、
    WebSearch がサブスクリプション認証(OAuth)を使うようにする。
    """
    claude_path = shutil.which("claude")
    if claude_path is None:
        raise RuntimeError("claude CLI が見つかりません。PATH を確認してください。")

    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    logger.info("claude CLI 呼び出し開始: %s (timeout=%ds)", label, timeout)
    try:
        model = get_model()
        result = subprocess.run(
            [claude_path, "-p", prompt, "--allowedTools", "WebSearch",
             "--model", model],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("claude CLI タイムアウト: %s (%ds)", label, timeout)
        raise RuntimeError(f"claude CLI がタイムアウトしました ({label})") from exc

    if result.returncode != 0:
        logger.error(
            "claude CLI エラー [%s] rc=%d\nstdout=%s\nstderr=%s",
            label, result.returncode, result.stdout, result.stderr,
        )
        detail = (result.stderr or result.stdout or "").strip()
        if len(detail) > 2000:
            detail = detail[:2000] + "…(truncated)"
        raise RuntimeError(f"claude CLI エラー [{label}] rc={result.returncode}: {detail}")

    logger.info("claude CLI 完了: %s (%d文字)", label, len(result.stdout))
    return result.stdout.strip()
