from datetime import date
from src.claude_runner import run_claude
from src.config import XssIntelConfig
from src.generator.prompt import render
from src.logger import get_logger
from src.prompt_safety import neutralize_user_text

logger = get_logger(__name__)


def generate_xss_report(config: XssIntelConfig) -> str:
    """claude CLI + WebSearch で XSS 脆弱性インテリジェンスレポートを生成"""
    frameworks = neutralize_user_text(", ".join(config.targets.frameworks))
    libraries = neutralize_user_text(", ".join(config.targets.libraries))
    keywords = neutralize_user_text(", ".join(config.targets.keywords))

    prompt = render(
        "xss_intel",
        frameworks=frameworks,
        libraries=libraries,
        keywords=keywords,
        date=date.today().strftime("%Y-%m-%d"),
    )

    logger.debug("対象フレームワーク: %s / ライブラリ: %s", frameworks, libraries)

    text = run_claude(prompt, "XSS Intel", timeout=300)
    logger.info("XSS レポート生成完了 (%d文字)", len(text))
    return text
