from concurrent.futures import ThreadPoolExecutor, as_completed
from src.claude_client import run_with_web_search
from src.config import BriefingConfig
from src.generator.prompt import render
from src.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT_MAIN = 300     # メイン分析（portfolio + geopolitical）
_TIMEOUT_SECTORS = 480  # セクタースイープ（14セクター × WebSearch）
# 並列実行のため実際の待機時間は max(MAIN, SECTORS) = 480s（合計ではない）


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


def _run_claude(prompt: str, label: str, timeout: int = _TIMEOUT_MAIN) -> str:
    """Anthropic SDK で claude を呼び出し、結果を返す。"""
    return run_with_web_search(prompt, label, timeout)


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
            executor.submit(_run_claude, main_prompt, "メイン分析", _TIMEOUT_MAIN): "main",
            executor.submit(_run_claude, sectors_prompt, "セクタースイープ", _TIMEOUT_SECTORS): "sectors",
        }
        results: dict[str, str] = {}
        errors: dict[str, str] = {}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                logger.error("claude CLI 失敗 [%s]: %s", key, e)
                errors[key] = str(e)

    if "main" in errors:
        # メイン分析が失敗した場合は続行不可
        raise RuntimeError(f"ブリーフィング生成に失敗しました: メイン分析\n{errors['main']}")

    assert "main" in results, "main result missing despite no error recorded"

    main_text = results["main"]

    if "sectors" in errors:
        # セクタースイープのみ失敗した場合は degraded モードで返す
        logger.warning("セクタースイープ失敗（メイン分析は成功）: %s", errors["sectors"])
        return main_text + "\n\n---\n\n⚠️ セクター動向の取得に失敗しました。\n" + errors["sectors"]

    assert "sectors" in results, "sectors result missing despite no error recorded"

    return main_text + "\n\n---\n\n## セクター動向\n\n" + results["sectors"]
