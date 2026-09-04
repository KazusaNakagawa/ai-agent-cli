"""Daily market briefing.

The pipeline itself is declared as a workflow in
``src/workflow/definitions/briefing.py``; the steps it references live here, so
that everything the briefing touches — config, fetchers, notifiers — stays in
one module. ``lambda_handler`` remains the entry point and keeps its original
signature and response shape for ``bin/run.sh``, the web run route and the
existing tests.
"""
from datetime import date

from src.charts.price_comparison import generate_price_comparison
from src.claude_runner import get_model
from src.config import CONFIG
from src.constants import (
    BRIEFING_CHART_PERIOD,
    BRIEFING_MD_RETENTION_DAYS,
    BRIEFING_MD_ROTATION_ENABLED,
    BRIEFING_OUTPUT_DIR,
    BRIEFING_SKIP_IF_EXISTS,
    CHART_OUTPUT_DIR,
)
from src.fetcher.fx import fetch_fx_context
from src.fetcher.stocks import fetch_stock_moves
from src.generator.briefing import generate_briefing, is_degraded_briefing, looks_like_briefing
from src.local_llm.briefing_index import index_briefings
from src.local_llm.config import load_config as load_local_llm_config
from src.metrics.briefing import extract_briefing_metrics
from src.notifier.discord import send_to_discord
from src.notifier.local_md import save_briefing_md
from src.notifier.notion import send_to_notion
from src.logger import get_logger
from src.utils import is_configured as _is_configured
from src.workflow.registry import get as get_workflow
from src.workflow.runner import run_workflow

logger = get_logger(__name__)


def _preflight() -> None:
    """Log a WARNING for each missing credential before the pipeline starts."""
    if not _is_configured(CONFIG.discord_token, CONFIG.discord_channel_id):
        logger.warning("DISCORD_TOKEN or CHANNEL_ID unset — skipping Discord notification")
    if not _is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id):
        logger.warning("NOTION_API_KEY or NOTION_DATABASE_ID unset — skipping Notion notification")


def _is_degraded_md(path) -> bool:
    """True when today's saved briefing is a half-failed body worth re-running.

    Unreadable files are treated as *not* degraded so an I/O problem keeps the
    idempotency guard intact rather than opening the door to duplicate paid runs.
    """
    try:
        return is_degraded_briefing(path.read_text(encoding="utf-8"))
    except OSError:
        logger.warning("could not read today's briefing MD (%s) — keeping the skip guard", path)
        return False


# --- workflow guard ---------------------------------------------------------


def briefing_guard(ctx) -> str | None:
    """Skip a second run on a day that already produced a real briefing.

    A degraded body does not count: it must not block the retry that would
    replace it, or the full briefing stays unobtainable until tomorrow.
    """
    if not BRIEFING_SKIP_IF_EXISTS:
        return None
    today_md = BRIEFING_OUTPUT_DIR / f"briefing_{date.today().strftime('%Y-%m-%d')}.md"
    if today_md.exists() and not _is_degraded_md(today_md):
        return f"already generated today ({today_md})"
    return None


# --- workflow steps ---------------------------------------------------------


def step_preflight(ctx) -> None:
    _preflight()


def step_fx(ctx) -> tuple[str, float | None]:
    """FX first: its day-over-day move is what converts each USD-quoted holding
    into the JPY move the holder actually experiences."""
    logger.info("fetching FX rates...")
    return fetch_fx_context(CONFIG)


def step_stocks(ctx) -> str:
    logger.info("fetching stock moves...")
    _, fx_change_pct = ctx.results["fx"]
    return fetch_stock_moves(CONFIG.portfolio.tickers, fx_change_pct)


def step_generate(ctx) -> str:
    logger.info("generating briefing (WebSearch)...")
    fx, _ = ctx.results["fx"]
    briefing = generate_briefing(ctx.results["stocks"], CONFIG, fx)
    logger.debug("briefing generated (length=%d)", len(briefing))

    if not looks_like_briefing(briefing):
        # Do not include the raw briefing text here — it can carry
        # user-specific financial/portfolio data and this message may end up
        # in logs or a monitoring service (review feedback on #410).
        raise RuntimeError(
            f"generated briefing does not look like a real briefing body (len={len(briefing)})"
        )
    return briefing


def step_persist(ctx) -> bool:
    """Write the local MD before any delivery, and report whether it landed.

    Only ``OSError`` is absorbed — a blanket catch would hide real defects
    while still returning 200. ``best_effort`` on the step would do exactly
    that, which is why the tolerance lives here instead.
    """
    try:
        save_briefing_md(
            ctx.results["generate"],
            BRIEFING_OUTPUT_DIR,
            BRIEFING_MD_RETENTION_DAYS,
            rotation_enabled=BRIEFING_MD_ROTATION_ENABLED,
        )
        return True
    except OSError as exc:
        logger.warning("local MD write failed: %s — continuing", exc)
        return False


def skip_index(ctx) -> bool:
    return not ctx.results["persist"]


def step_index(ctx) -> None:
    """Index today's briefing for cross-date chat RAG (#395).

    The experimental local-LLM stack (Ollama/Chroma) is not guaranteed to be
    running, so a failure here is logged and swallowed — it must never block
    the primary Discord/Notion/local-MD deliveries.

    The tolerance lives in the step rather than in ``Step.best_effort`` so the
    warning keeps naming what actually failed. The runner's generic message
    would say only that a step called ``index`` failed, which is a worse thing
    to find in the morning's log.
    """
    try:
        index_briefings(load_local_llm_config())
    except Exception as exc:  # noqa: BLE001
        logger.warning("briefing indexing into chromadb failed: %s — continuing", exc)


def skip_chart(ctx) -> bool:
    """Skip the render when nothing can carry the result.

    Rendering costs a yfinance download, and the chart's only consumer today is
    the Discord attachment — so an unconfigured Discord means the work has no
    destination. Delegating to ``skip_discord`` keeps that coupling in one
    predicate: when a second consumer appears, this is the only place to widen.
    """
    return skip_discord(ctx)


def step_chart(ctx) -> str:
    """Render the portfolio comparison chart delivered with the briefing.

    Declared ``best_effort``: the chart is an illustration of the text, so a
    yfinance outage must cost the reader the picture and not the briefing.
    """
    logger.info("rendering portfolio chart...")
    path = generate_price_comparison(
        list(CONFIG.portfolio.tickers), CHART_OUTPUT_DIR, BRIEFING_CHART_PERIOD
    )
    logger.info("chart written: %s", path)
    return str(path)


def skip_discord(ctx) -> bool:
    return not _is_configured(CONFIG.discord_token, CONFIG.discord_channel_id)


def step_deliver_discord(ctx) -> None:
    logger.info("sending to Discord...")
    # .get(): a failed best-effort step records no result, so the delivery has
    # to tolerate the key being absent entirely.
    send_to_discord(
        ctx.results["generate"],
        CONFIG.discord_token,
        CONFIG.discord_channel_id,
        attachment=ctx.results.get("chart"),
    )


def skip_notion(ctx) -> bool:
    return not _is_configured(CONFIG.notion_api_key, CONFIG.notion_database_id)


def step_deliver_notion(ctx) -> str | None:
    logger.info("creating Notion page...")
    briefing = ctx.results["generate"]
    notion_text = briefing + f"\n\n---\nModel: {get_model()}"
    metrics = extract_briefing_metrics(briefing, CONFIG.portfolio.tickers)
    page_url = send_to_notion(
        notion_text,
        CONFIG.notion_api_key,
        CONFIG.notion_database_id,
        title=f"マーケットブリーフィング — {date.today().strftime('%Y-%m-%d')}",
        tags=["agent"],
        extra_properties=metrics,
    )
    if page_url:
        logger.info("Notion ページ: %s", page_url)
    return page_url


# --- entry point ------------------------------------------------------------


def lambda_handler(event=None, context=None, *, dry_run: bool = False, force: bool = False):
    """Run the briefing workflow and return the legacy response shape."""
    logger.info("=== My World Briefing start ===")

    record = run_workflow(get_workflow("briefing"), force=force, dry_run=dry_run)

    if record.status == "dry_run":
        logger.info("Dry-run mode — skipping the pipeline")
        return {"statusCode": 200, "body": "dry-run"}

    if record.status == "skipped":
        logger.info(
            "Briefing already generated today (%s) — skipping. Pass --force to override.",
            record.skip_reason,
        )
        return {"statusCode": 200, "body": "skipped (already generated today)"}

    logger.info("=== done ===")
    return {"statusCode": 200, "body": "Briefing sent.", "md_written": record.results["persist"]}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="My World Briefing agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate credentials and config without running the pipeline")
    parser.add_argument("--force", action="store_true",
                        help="Run even if today's briefing MD already exists (overrides BRIEFING_SKIP_IF_EXISTS)")
    args = parser.parse_args()
    lambda_handler(dry_run=args.dry_run, force=args.force)
