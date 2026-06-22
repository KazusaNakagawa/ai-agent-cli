from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from src.claude_runner import run_claude
from src.config import BriefingConfig
from src.constants import TIMEOUT_BRIEFING_MAIN, TIMEOUT_BRIEFING_SECTORS
from src.generator.prompt import render
from src.logger import get_logger
from src.prompt_safety import neutralize_user_text

logger = get_logger(__name__)

# Because of parallel execution, actual wait time is max(MAIN, SECTORS) = 480s (not the sum).

# Few-shot example captured from a high-capability model's output. Injected into
# the main briefing prompt so cheaper models keep the structure (#192). See
# prompts/examples/README.md for the regeneration steps.
_FEW_SHOT_PATH = Path(__file__).parents[2] / "prompts" / "examples" / "briefing_few_shot.md"


@lru_cache(maxsize=1)
def load_briefing_few_shot() -> str:
    """Load and return the main briefing few-shot example.

    The few-shot is passed as a **value** to ``render()``, so any ``$`` in its
    body is never reinterpreted as a placeholder (single-pass substitution).

    The asset ships with the repo and does not change at runtime, so ``lru_cache``
    reads it once to avoid disk I/O on every ``generate_briefing()`` call.
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
    """Generate the briefing by running the main analysis and sector sweep in parallel."""
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
                logger.error("claude CLI failed [%s]: %s", key, e)
                errors[key] = str(e)

    if "main" in errors:
        raise RuntimeError(f"briefing generation failed: main analysis\n{errors['main']}")

    assert "main" in results, "main result missing despite no error recorded"

    main_text = results["main"]

    if "sectors" in errors:
        logger.warning("sector sweep failed (main analysis succeeded): %s", errors["sectors"])
        return main_text + "\n\n---\n\n⚠️ セクター動向の取得に失敗しました。\n" + errors["sectors"]

    assert "sectors" in results, "sectors result missing despite no error recorded"

    return main_text + "\n\n---\n\n## セクター動向\n\n" + results["sectors"]
