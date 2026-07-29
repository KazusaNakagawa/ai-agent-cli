from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from src.claude_runner import run_claude
from src.config import BriefingConfig
from src.constants import RETRY_MAX_ATTEMPTS_BRIEFING, TIMEOUT_BRIEFING_MAIN, TIMEOUT_BRIEFING_SECTORS
from src.generator.prompt import render
from src.logger import get_logger
from src.prompt_safety import neutralize_user_text

logger = get_logger(__name__)

# Because of parallel execution, worst-case wait is max(MAIN, SECTORS), not the sum.

# Few-shot example captured from a high-capability model's output. Injected into
# the main briefing prompt so cheaper models keep the structure (#192). See
# prompts/examples/README.md for the regeneration steps.
_FEW_SHOT_PATH = Path(__file__).parents[2] / "prompts" / "examples" / "briefing_few_shot.md"

# Minimum character count for a plausible briefing body. Below this, even a
# heading-bearing string is more likely a stray status message than real content.
_MIN_BRIEFING_LENGTH = 200

# How far into the text a "### " heading may appear and still count. The
# claude CLI often prepends a short conversational preamble (e.g.
# "情報が揃いました。ブリーフィングをまとめます。\n\n---\n\n", observed in
# production, #410) before the actual heading, so an exact startswith check
# is too strict and rejects real output. A hijacked skill report (#409) never
# contains a "### " heading at all, so this window still rejects it while
# tolerating a realistic preamble.
_HEADING_SEARCH_WINDOW = 500

# Cap for the error detail quoted at the top of a degraded (sectors-only) body,
# kept well inside _HEADING_SEARCH_WINDOW. See _truncate_error.
_ERROR_NOTE_MAX_LENGTH = 200

# Notices marking a body where one half of the pipeline failed. They are the
# on-disk signal that today's briefing is incomplete, so handler.py can let a
# retry through instead of reporting "already generated today".
MAIN_FAILED_NOTICE = "⚠️ メイン分析の取得に失敗しました。セクター動向のみお届けします。"
SECTORS_FAILED_NOTICE = "⚠️ セクター動向の取得に失敗しました。"


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


def looks_like_briefing(text: str) -> bool:
    """Heuristic check that ``text`` is a real generated briefing body.

    Guards against a claude CLI call being hijacked by an unrelated skill
    mid-run (#409): the skill's own short completion report gets returned
    instead of the actual briefing, which would otherwise silently overwrite
    the local MD file (and Discord/Notion deliveries) with junk. A real
    briefing always contains a "### " heading (enforced by the few-shot
    example) near the start — allowing for a short conversational preamble —
    and runs well past a short status line. A hijacked skill report never
    contains one at all.
    """
    return len(text) >= _MIN_BRIEFING_LENGTH and "### " in text[:_HEADING_SEARCH_WINDOW]


def is_degraded_briefing(text: str) -> bool:
    """True when ``text`` is a briefing whose main analysis or sector sweep failed.

    Used by the idempotency guard in handler.py: the guard exists to stop a
    duplicate *successful* run, so a half-failed body must not count as "today's
    briefing" and lock out the retry that would produce the full one.
    """
    return MAIN_FAILED_NOTICE in text or SECTORS_FAILED_NOTICE in text


def _truncate_error(detail: str) -> str:
    """Shorten an error detail so it can head a degraded briefing body.

    run_claude truncates its CLI error detail at 2000 chars, which would push
    the sector sweep's first "### " heading past _HEADING_SEARCH_WINDOW and make
    looks_like_briefing reject the very body this fallback exists to save.
    """
    if len(detail) <= _ERROR_NOTE_MAX_LENGTH:
        return detail
    return detail[:_ERROR_NOTE_MAX_LENGTH] + "…(truncated)"


def generate_briefing(stocks: str, config: BriefingConfig, fx: str = "") -> str:
    """Generate the briefing by running the main analysis and sector sweep in parallel.

    ``fx`` is the pre-rendered exchange-rate block. It defaults to empty so a
    failed FX fetch (or no configured pair) degrades to the previous USD-only
    briefing rather than blocking the run.
    """
    tickers = join_safe(config.portfolio.tickers, sep=", ")
    themes = join_safe(config.portfolio.themes, sep=", ")

    main_prompt = render(
        "briefing",
        tickers=tickers,
        themes=themes,
        geopolitical=build_geopolitical_context(config),
        watch_events=build_watch_events_context(config),
        stocks=stocks,
        fx=fx or "(為替の取得なし。為替セクションは省略してよい)",
        few_shot=load_briefing_few_shot(),
    )
    sectors_prompt = render(
        "briefing_sectors",
        watch_sectors=build_watch_sectors_context(config),
        stocks=stocks,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(
                run_claude, main_prompt, "メイン分析", TIMEOUT_BRIEFING_MAIN,
                max_attempts=RETRY_MAX_ATTEMPTS_BRIEFING,
            ): "main",
            executor.submit(
                run_claude, sectors_prompt, "セクタースイープ", TIMEOUT_BRIEFING_SECTORS,
                max_attempts=RETRY_MAX_ATTEMPTS_BRIEFING,
            ): "sectors",
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
        if "sectors" not in results:
            raise RuntimeError(f"briefing generation failed: main analysis\n{errors['main']}")
        logger.warning(
            "main analysis failed (sector sweep succeeded) — delivering a "
            "sectors-only briefing: %s",
            errors["main"],
        )
        return (
            f"{MAIN_FAILED_NOTICE}\n"
            f"{_truncate_error(errors['main'])}\n\n---\n\n"
            "## セクター動向\n\n" + results["sectors"]
        )

    assert "main" in results, "main result missing despite no error recorded"

    main_text = results["main"]

    if "sectors" in errors:
        logger.warning("sector sweep failed (main analysis succeeded): %s", errors["sectors"])
        return main_text + f"\n\n---\n\n{SECTORS_FAILED_NOTICE}\n" + errors["sectors"]

    assert "sectors" in results, "sectors result missing despite no error recorded"

    return main_text + "\n\n---\n\n## セクター動向\n\n" + results["sectors"]
