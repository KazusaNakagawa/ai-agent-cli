import subprocess
from src.config import BriefingConfig
from src.generator.prompt import render
from src.logger import get_logger

logger = get_logger(__name__)


def _build_geopolitical_context(config: BriefingConfig) -> str:
    lines = []
    for c in config.geopolitical.conflicts:
        sectors = "、".join(c.affected_sectors)
        tickers = "、".join(c.related_tickers)
        entry = f"### {c.name}\n- 影響セクター: {sectors}"
        if tickers:
            entry += f"\n- 関連銘柄: {tickers}"
        if c.notes:
            entry += f"\n- 背景: {c.notes}"
        lines.append(entry)
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
