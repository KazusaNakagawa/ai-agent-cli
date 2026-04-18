import shutil
import subprocess
from src.config import BriefingConfig
from src.generator.prompt import render
from src.logger import get_logger

logger = get_logger(__name__)


def _build_geopolitical_context(config: BriefingConfig) -> str:
    """BriefingConfig の地政学リスク情報をプロンプト用のテキストブロックに整形して返す。"""
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


def _build_watch_sectors_context(config: BriefingConfig) -> str:
    """watch_sectors をプロンプト用のテキストブロックに整形して返す。"""
    lines = []
    for s in config.watch_sectors:
        tickers = "、".join(s.tickers)
        entry = f"### {s.sector}\n- 銘柄: {tickers}"
        if s.notes:
            entry += f"\n- 注目点: {s.notes}"
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
        watch_sectors=_build_watch_sectors_context(config),
        stocks=stocks,
    )

    logger.info("claude CLI (WebSearch) 呼び出し開始")
    logger.debug("対象銘柄: %s / テーマ: %s", tickers, themes)

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
        logger.error("claude CLI がタイムアウトしました")
        raise RuntimeError("claude CLI の実行がタイムアウトしました")

    if result.returncode != 0:
        logger.error("claude CLI エラー: %s", result.stderr)
        raise RuntimeError(f"claude CLI エラー: {result.stderr}")

    logger.info("ブリーフィング生成完了 (%d文字)", len(result.stdout))
    return result.stdout.strip()
