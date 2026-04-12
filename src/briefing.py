import subprocess
from src.config import BriefingConfig
from src.prompt import render
from src.logger import get_logger

logger = get_logger(__name__)


def _build_geopolitical_context(config: BriefingConfig) -> str:
    lines = []
    for c in config.geopolitical.conflicts:
        sectors = "、".join(c.affected_sectors)
        tickers = "、".join(c.related_tickers)
        lines.append(
            f"### {c.name}\n"
            f"- 影響セクター: {sectors}\n"
            f"- 関連銘柄: {tickers}\n"
            f"- 背景: {c.notes}"
        )
    return "\n\n".join(lines)


def generate_briefing(stocks: str, config: BriefingConfig) -> str:
    """claude CLI + WebSearch でブリーフィングを生成"""
    tickers = ", ".join(config.portfolio.tickers)
    themes = ", ".join(config.portfolio.themes)

    prompt = render(
        "briefing",
        tickers=tickers,
        themes=themes,
        geopolitical=_build_geopolitical_context(config),
        stocks=stocks,
    )

    logger.info("claude CLI (WebSearch) 呼び出し開始")
    logger.debug("対象銘柄: %s / テーマ: %s", tickers, themes)

    result = subprocess.run(
        ["claude", "-p", prompt, "--allowedTools", "WebSearch"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("claude CLI エラー: %s", result.stderr)
        raise RuntimeError(f"claude CLI エラー: {result.stderr}")

    logger.info("ブリーフィング生成完了 (%d文字)", len(result.stdout))
    return result.stdout.strip()
