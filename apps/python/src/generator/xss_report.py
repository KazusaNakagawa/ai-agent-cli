from datetime import date
from src.claude_runner import run_claude
from src.config import XssIntelConfig
from src.constants import TIMEOUT_CLAUDE_DEFAULT
from src.generator.prompt import render
from src.logger import get_logger
from src.prompt_safety import neutralize_user_text

logger = get_logger(__name__)


def generate_xss_report(config: XssIntelConfig) -> str:
    """Generate the XSS vulnerability intelligence report via claude CLI + WebSearch."""
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

    logger.debug("target frameworks: %s / libraries: %s", frameworks, libraries)

    text = run_claude(prompt, "XSS Intel", timeout=TIMEOUT_CLAUDE_DEFAULT)
    logger.info("XSS report generated (%d chars)", len(text))
    return text
