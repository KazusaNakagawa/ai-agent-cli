import shutil
import subprocess
from datetime import date
from src.config import XssIntelConfig
from src.generator.prompt import render
from src.logger import get_logger

logger = get_logger(__name__)


def generate_xss_report(config: XssIntelConfig) -> str:
    """claude CLI + WebSearch で XSS 脆弱性インテリジェンスレポートを生成"""
    frameworks = ", ".join(config.targets.frameworks)
    libraries = ", ".join(config.targets.libraries)
    keywords = ", ".join(config.targets.keywords)

    prompt = render(
        "xss_intel",
        frameworks=frameworks,
        libraries=libraries,
        keywords=keywords,
        date=date.today().strftime("%Y-%m-%d"),
    )

    logger.info("claude CLI (WebSearch) 呼び出し開始 [XSS Intel]")
    logger.debug("対象フレームワーク: %s / ライブラリ: %s", frameworks, libraries)

    claude_path = shutil.which("claude")
    if claude_path is None:
        raise RuntimeError("claude CLI が見つかりません。PATH を確認してください。")

    try:
        result = subprocess.run(
            [claude_path, "-p", prompt, "--allowedTools", "WebSearch"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        logger.error("claude CLI がタイムアウトしました [XSS Intel]")
        raise RuntimeError("claude CLI の実行がタイムアウトしました")

    if result.returncode != 0:
        logger.error("claude CLI エラー: %s", result.stderr)
        raise RuntimeError(f"claude CLI エラー: {result.stderr}")

    logger.info("XSS レポート生成完了 (%d文字)", len(result.stdout))
    return result.stdout.strip()
