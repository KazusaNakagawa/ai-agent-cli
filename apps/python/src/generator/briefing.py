from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from src.claude_runner import run_claude
from src.config import BriefingConfig
from src.constants import TIMEOUT_BRIEFING_MAIN, TIMEOUT_BRIEFING_SECTORS
from src.generator.prompt import render
from src.logger import get_logger
from src.prompt_safety import neutralize_user_text

logger = get_logger(__name__)

# 並列実行のため実際の待機時間は max(MAIN, SECTORS) = 480s（合計ではない）

# 高性能モデル出力を捕捉した few-shot 例。安価なモデルでも構成を保てるよう
# メインブリーフィングのプロンプトに注入する（#192）。再生成手順は
# prompts/examples/README.md を参照。
_FEW_SHOT_PATH = Path(__file__).parents[2] / "prompts" / "examples" / "briefing_few_shot.md"


def load_briefing_few_shot() -> str:
    """メインブリーフィングの few-shot 例を読み込んで返す。

    few-shot は ``render()`` の **値** として渡るため、本文中の ``$`` が
    プレースホルダとして再解釈されることはない（単一パス置換）。
    """
    return _FEW_SHOT_PATH.read_text(encoding="utf-8")


def join_safe(items: list[str], sep: str = "、") -> str:
    """Join user-supplied list items after neutralizing each element.

    Joining alone is not safe because an attacker who controls config can put
    a newline + role marker inside a single element and end up with
    ``"NVDA\\nSYSTEM: ..."`` at line start in the rendered prompt.
    """
    return sep.join(neutralize_user_text(item) for item in items)


def build_geopolitical_context(config: BriefingConfig) -> str:
    """Return Markdown-formatted geopolitical conflicts for prompt injection."""
    lines = []
    for c in config.geopolitical.conflicts:
        sectors = join_safe(c.affected_sectors)
        tickers = join_safe(c.related_tickers)
        entry = f"### {neutralize_user_text(c.name)}\n- 影響セクター: {sectors}"
        if tickers:
            entry += f"\n- 関連銘柄: {tickers}"
        if c.notes:
            entry += f"\n- 背景: {neutralize_user_text(c.notes)}"
        lines.append(entry)
    return "\n\n".join(lines)


def build_watch_sectors_context(config: BriefingConfig) -> str:
    """Return Markdown-formatted watch sectors for prompt injection."""
    lines = []
    for s in config.watch_sectors:
        tickers = join_safe(s.tickers)
        entry = f"### {neutralize_user_text(s.sector)}\n- 銘柄: {tickers}"
        if s.notes:
            entry += f"\n- 注目点: {neutralize_user_text(s.notes)}"
        lines.append(entry)
    return "\n\n".join(lines)


def build_watch_events_context(config: BriefingConfig) -> str:
    """Return Markdown-formatted watch events for prompt injection; empty string when none configured."""
    if not config.watch_events:
        return ""
    lines = []
    for event in config.watch_events:
        entry = (
            f"### {neutralize_user_text(event.name)}\n"
            f"- トリガー: {neutralize_user_text(event.trigger)}"
        )
        if event.affected_sectors:
            entry += f"\n- 影響セクター: {join_safe(event.affected_sectors)}"
        if event.related_tickers:
            entry += f"\n- 関連銘柄: {join_safe(event.related_tickers)}"
        if event.notes:
            entry += f"\n- 背景: {neutralize_user_text(event.notes)}"
        lines.append(entry)
    return "\n\n".join(lines)


def generate_briefing(stocks: str, config: BriefingConfig) -> str:
    """メイン分析とセクタースイープを並列実行してブリーフィングを生成する。"""
    tickers = join_safe(config.portfolio.tickers, sep=", ")
    themes = join_safe(config.portfolio.themes, sep=", ")

    main_prompt = render(
        "briefing",
        tickers=tickers,
        themes=themes,
        geopolitical=build_geopolitical_context(config),
        watch_events=build_watch_events_context(config),
        stocks=stocks,
        few_shot=load_briefing_few_shot(),
    )
    sectors_prompt = render(
        "briefing_sectors",
        watch_sectors=build_watch_sectors_context(config),
        stocks=stocks,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(run_claude, main_prompt, "メイン分析", TIMEOUT_BRIEFING_MAIN): "main",
            executor.submit(run_claude, sectors_prompt, "セクタースイープ", TIMEOUT_BRIEFING_SECTORS): "sectors",
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
        raise RuntimeError(f"ブリーフィング生成に失敗しました: メイン分析\n{errors['main']}")

    assert "main" in results, "main result missing despite no error recorded"

    main_text = results["main"]

    if "sectors" in errors:
        logger.warning("セクタースイープ失敗（メイン分析は成功）: %s", errors["sectors"])
        return main_text + "\n\n---\n\n⚠️ セクター動向の取得に失敗しました。\n" + errors["sectors"]

    assert "sectors" in results, "sectors result missing despite no error recorded"

    return main_text + "\n\n---\n\n## セクター動向\n\n" + results["sectors"]
