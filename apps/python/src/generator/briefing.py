import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from src.claude_runner import run_claude
from src.config import BriefingConfig
from src.constants import (
    BRIEFSCRIPT_VALIDATION_MAX_ATTEMPTS,
    RETRY_MAX_ATTEMPTS_BRIEFING,
    TIMEOUT_BRIEFING_HOLDINGS,
    TIMEOUT_BRIEFING_MAIN,
    TIMEOUT_BRIEFING_SECTORS,
)
from src.fetcher.stocks import StockQuote
from src.generator.briefscript_render import (
    render_document_markdown,
    render_sectors_markdown,
    snapshot_market,
    splice_holdings,
)
from src.generator.briefscript_schema import (
    BriefingDocument,
    HoldingsBlock,
    HoldingsSection,
    MainBlock,
    MainSection,
    MarkdownSection,
    SectorsBlock,
    SectorsSection,
    holdings_json_schema,
    main_json_schema,
    parse_holdings_section,
    parse_main_section,
    parse_sectors_section,
    sectors_json_schema,
)
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

# Heading that opens the sector sweep section. Shared so a recovery run splices
# in the same heading the main pipeline writes, and recovery_handler can mark
# its Notion append as a recovery without diverging from this wording.
SECTORS_HEADING = "## セクター動向"


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


def looks_like_briefing_document(doc: BriefingDocument) -> bool:
    """``looks_like_briefing`` for the IR (#515).

    A structured main analysis already passed schema validation, which a
    hijacked skill report (#409) cannot; only Markdown bodies need the text
    heuristic.
    """
    if any(isinstance(section, MainBlock) for section in doc.sections):
        return True
    return looks_like_briefing(render_document_markdown(doc))


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


def _watch_sector_names(config: BriefingConfig) -> list[str]:
    # Normalised once, so the schema enum, validation and rendering agree.
    return list(dict.fromkeys(
        " ".join(s.sector.split()) for s in config.watch_sectors if s.sector.strip()
    ))


def generate_sectors_section(stocks: str, config: BriefingConfig) -> SectorsSection:
    """Run the sector sweep as validated BriefScript (#514)."""
    sectors = _watch_sector_names(config)
    prompt = render(
        "briefing_sectors",
        watch_sectors=build_watch_sectors_context(config),
        stocks=stocks,
    )
    return _generate_validated(
        prompt, "セクタースイープ", TIMEOUT_BRIEFING_SECTORS, sectors_json_schema(sectors),
        lambda data: parse_sectors_section(data, sectors=sectors),
    )


def generate_sectors(stocks: str, config: BriefingConfig) -> str:
    """Run the sector sweep on its own and return its rendered body.

    Split out of generate_briefing so the wake-up recovery job (#432) can redo
    just this half after a sleep-severed run, without paying for a second main
    analysis.
    """
    section = generate_sectors_section(stocks, config)
    return render_sectors_markdown(section, _watch_sector_names(config))


def merge_recovered_sectors(body: str, sectors: str) -> str:
    """Splice a recovered sector sweep into a briefing body that failed to get one.

    Everything from SECTORS_FAILED_NOTICE onward is the failure notice plus the
    quoted CLI error, so the whole tail is replaced by the real section. A body
    without the notice is returned untouched, which keeps the recovery run
    idempotent.
    """
    marker = body.find(SECTORS_FAILED_NOTICE)
    if marker == -1:
        return body
    return body[:marker] + f"{SECTORS_HEADING}\n\n" + sectors


class BriefScriptError(RuntimeError):
    """A BriefScript section never validated; callers fall back per section."""


def _holding_tickers(config: BriefingConfig) -> list[str]:
    # Trimmed and de-duplicated once, so the prompt, the schema enum, validation
    # and the quote lookup all agree (quotes are keyed by the trimmed form).
    return list(dict.fromkeys(t.strip() for t in config.portfolio.tickers if t.strip()))


def _generate_validated(prompt: str, label: str, timeout: int, schema: dict, parse):
    """Call claude with ``--json-schema`` and validate, retrying once on bad output.

    Output that fails validation is retried with the error appended, so the
    model can correct exactly what was wrong (#504). A CLI failure is not
    retried here — run_claude already spent its transient-error budget.
    """
    base_prompt = prompt
    last_error = ""
    for attempt in range(1, BRIEFSCRIPT_VALIDATION_MAX_ATTEMPTS + 1):
        raw = run_claude(
            prompt, label, timeout,
            max_attempts=RETRY_MAX_ATTEMPTS_BRIEFING, json_schema=schema,
        )
        try:
            return parse(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)
            logger.warning(
                "%s BriefScript failed validation (attempt %d/%d): %s",
                label, attempt, BRIEFSCRIPT_VALIDATION_MAX_ATTEMPTS, _truncate_error(last_error),
            )
            prompt = (
                f"{base_prompt}\n\n## 前回の出力のエラー\n"
                f"前回の出力は次の検証エラーで却下されました。直して出力し直してください。\n{last_error}"
            )
    raise BriefScriptError(f"{label} BriefScript invalid after retries: {_truncate_error(last_error)}")


def generate_holdings(stocks: str, config: BriefingConfig) -> HoldingsSection:
    """Generate the holdings section as validated BriefScript."""
    tickers = _holding_tickers(config)
    prompt = render("briefing_holdings", tickers=join_safe(tickers, sep=", "), stocks=stocks)
    return _generate_validated(
        prompt, "保有銘柄示唆", TIMEOUT_BRIEFING_HOLDINGS, holdings_json_schema(tickers),
        lambda data: parse_holdings_section(data, holdings=tickers),
    )


def generate_main_section(prompt: str) -> MainSection:
    """Run the main analysis as validated BriefScript (#515)."""
    return _generate_validated(
        prompt, "メイン分析", TIMEOUT_BRIEFING_MAIN, main_json_schema(), parse_main_section,
    )


# Stands in for the few-shot's holdings body in BriefScript mode.
_FEW_SHOT_HOLDINGS_NOTE = "（保有銘柄ごとの示唆は別の処理が書く）"


def _main_prompt_holdings_parts(tickers: str, briefscript: bool) -> dict[str, str]:
    """Prompt pieces that differ between the two holdings modes.

    With BriefScript the holdings are researched and written by their own call,
    so the main analysis is told to skip both — that is the duplicate spend
    #511 removes. The few-shot's holdings body is swapped for a note, or the
    example would keep modelling the old section.
    """
    # Literal template names only (see test_prompt's render call-site guard).
    few_shot = load_briefing_few_shot()
    if briefscript:
        holdings_format = ""
        research = render("briefing_ticker_research_briefscript", tickers=tickers)
        guidance = render("briefing_holdings_guidance_briefscript")
        few_shot = splice_holdings(few_shot, _FEW_SHOT_HOLDINGS_NOTE) or few_shot
    else:
        holdings_format = render("briefing_holdings_format_markdown")
        research = render("briefing_ticker_research_markdown", tickers=tickers)
        guidance = render("briefing_holdings_guidance_markdown")
    return {
        "ticker_research": research.rstrip("\n"),
        "holdings_guidance": guidance.rstrip("\n"),
        "holdings_format": holdings_format.rstrip("\n"),
        "few_shot": few_shot,
    }


def _sectors_block(section: SectorsSection, config: BriefingConfig) -> SectorsBlock:
    return SectorsBlock(sectors=_watch_sector_names(config), content=section)


def generate_briefing_document(
    stocks: str,
    config: BriefingConfig,
    fx: str = "",
    quotes: dict[str, StockQuote] | None = None,
    fx_change_pct: float | None = None,
    today: date | None = None,
) -> BriefingDocument:
    """Generate the briefing by running the main analysis and sector sweep in parallel.

    ``fx`` is the pre-rendered exchange-rate block. It defaults to empty so a
    failed FX fetch (or no configured pair) degrades to the previous USD-only
    briefing rather than blocking the run. It is stored in the snapshot, so
    the FX section shows the fetched figures, not the model's.

    With ``quotes``, the briefing is BriefScript: the main analysis (#515),
    the holdings (#506) and the sector sweep each return validated JSON. If
    the holdings call fails, its section falls back to quote-derived headings
    with a note. Without quotes the main analysis is the Markdown prompt.

    The result is the whole briefing as IR (#513).
    """
    briefscript = bool(quotes)
    tickers = join_safe(config.portfolio.tickers, sep=", ")
    themes = join_safe(config.portfolio.themes, sep=", ")

    main_parts = dict(
        tickers=tickers,
        themes=themes,
        geopolitical=build_geopolitical_context(config),
        watch_events=build_watch_events_context(config),
        stocks=stocks,
        fx=fx or "(為替の取得なし。為替セクションは省略してよい)",
        **_main_prompt_holdings_parts(tickers, briefscript=briefscript),
    )
    with ThreadPoolExecutor(max_workers=3) as executor:
        if briefscript:
            main = executor.submit(generate_main_section, render("briefing_main", **main_parts))
        else:
            main = executor.submit(
                run_claude, render("briefing", **main_parts), "メイン分析", TIMEOUT_BRIEFING_MAIN,
                max_attempts=RETRY_MAX_ATTEMPTS_BRIEFING,
            )
        futures = {
            main: "main",
            executor.submit(generate_sectors_section, stocks, config): "sectors",
        }
        if briefscript:
            futures[executor.submit(generate_holdings, stocks, config)] = "holdings"
        results: dict = {}
        errors: dict[str, str] = {}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                if key == "holdings":
                    logger.warning("holdings BriefScript failed, falling back to Markdown: %s", e)
                else:
                    logger.error("claude CLI failed [%s]: %s", key, e)
                errors[key] = str(e)

    market = snapshot_market(quotes, fx_change_pct)
    market.fx_context = fx
    doc = BriefingDocument(date=today or date.today(), market=market)

    if "main" in errors:
        if "sectors" not in results:
            raise RuntimeError(f"briefing generation failed: main analysis\n{errors['main']}")
        logger.warning(
            "main analysis failed (sector sweep succeeded) — delivering a "
            "sectors-only briefing: %s",
            errors["main"],
        )
        doc.sections = [
            MarkdownSection(
                text=f"{MAIN_FAILED_NOTICE}\n{_truncate_error(errors['main'])}\n\n---\n\n"
                f"{SECTORS_HEADING}\n\n",
            ),
            _sectors_block(results["sectors"], config),
        ]
        return doc

    assert "main" in results, "main result missing despite no error recorded"

    if briefscript:
        # Without content the holdings block renders quote-derived headings
        # and a note: the main analysis was told not to write holdings (#511).
        holdings = HoldingsBlock(tickers=_holding_tickers(config), content=results.get("holdings"))
        doc.sections = [MainBlock(content=results["main"], holdings=holdings)]
    else:
        doc.sections = [MarkdownSection(text=results["main"])]

    if "sectors" in errors:
        logger.warning("sector sweep failed (main analysis succeeded): %s", errors["sectors"])
        doc.sections.append(
            MarkdownSection(text=f"\n\n---\n\n{SECTORS_FAILED_NOTICE}\n" + errors["sectors"]),
        )
        return doc

    assert "sectors" in results, "sectors result missing despite no error recorded"

    doc.sections += [
        MarkdownSection(text=f"\n\n---\n\n{SECTORS_HEADING}\n\n"),
        _sectors_block(results["sectors"], config),
    ]
    return doc


def generate_briefing(*args, **kwargs) -> str:
    """``generate_briefing_document`` rendered to the briefing Markdown."""
    return render_document_markdown(generate_briefing_document(*args, **kwargs))
