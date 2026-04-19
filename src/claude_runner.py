import os
import shutil
import subprocess
from src.logger import get_logger

logger = get_logger(__name__)


def run_claude(prompt: str, label: str, timeout: int = 300) -> str:
    """claude CLI を subprocess で呼び出し、結果を返す。

    ANTHROPIC_API_KEY を子プロセスに渡さないことで、
    WebSearch がサブスクリプション認証（OAuth）を使うようにする。
    """
    claude_path = shutil.which("claude")
    if claude_path is None:
        raise RuntimeError("claude CLI が見つかりません。PATH を確認してください。")

    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    logger.info("claude CLI 呼び出し開始: %s (timeout=%ds)", label, timeout)
    try:
        result = subprocess.run(
            [claude_path, "-p", prompt, "--allowedTools", "WebSearch"],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except subprocess.TimeoutExpired:
        logger.error("claude CLI タイムアウト: %s (%ds)", label, timeout)
        raise RuntimeError(f"claude CLI がタイムアウトしました ({label})")

    if result.returncode != 0:
        logger.error("claude CLI エラー [%s] rc=%d: %s", label, result.returncode, result.stdout or result.stderr)
        raise RuntimeError(f"claude CLI エラー [{label}]: {result.stdout or result.stderr}")

    logger.info("claude CLI 完了: %s (%d文字)", label, len(result.stdout))
    return result.stdout.strip()
