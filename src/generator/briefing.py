import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.config import BriefingConfig
from src.generator.prompt import render
from src.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 300


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


def _run_claude(prompt: str, label: str) -> str:
    """claude CLI を subprocess で呼び出し、結果を返す。"""
    claude_path = shutil.which("claude")
    if claude_path is None:
        raise RuntimeError("claude CLI が見つかりません。PATH を確認してください。")

    logger.info("claude CLI 呼び出し開始: %s", label)
    try:
        result = subprocess.run(
            [claude_path, "-p", prompt, "--allowedTools", "WebSearch"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.error("claude CLI タイムアウト: %s (%ds)", label, _TIMEOUT)
        raise RuntimeError(f"claude CLI がタイムアウトしました ({label})")

    if result.returncode != 0:
        logger.error("claude CLI エラー [%s]: %s", label, result.stderr)
        raise RuntimeError(f"claude CLI エラー [{label}]: {result.stderr}")

    logger.info("claude CLI 完了: %s (%d文字)", label, len(result.stdout))
    return result.stdout.strip()


def generate_briefing(stocks: str, config: BriefingConfig) -> str:
    """メイン分析とセクタースイープを並列実行してブリーフィングを生成する。"""
    tickers = ", ".join(config.portfolio.tickers)
    themes = ", ".join(config.portfolio.themes)

    main_prompt = render(
        "briefing",
        tickers=tickers,
        themes=themes,
        geopolitical=_build_geopolitical_context(config),
        stocks=stocks,
    )
    sectors_prompt = render(
        "briefing_sectors",
        watch_sectors=_build_watch_sectors_context(config),
        stocks=stocks,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_run_claude, main_prompt, "メイン分析"): "main",
            executor.submit(_run_claude, sectors_prompt, "セクタースイープ"): "sectors",
        }
        results = {}
        for future in as_completed(futures):
            key = futures[future]
            results[key] = future.result()

    return results["main"] + "\n\n" + results["sectors"]
