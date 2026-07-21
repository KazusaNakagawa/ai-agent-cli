"""Generate the weekly briefing summary."""
from datetime import date, timedelta

from src.claude_runner import get_model, run_claude
from src.constants import TIMEOUT_WEEKLY_SUMMARY
from src.generator.prompt import render
from src.logger import get_logger
from src.prompt_safety import wrap_untrusted

logger = get_logger(__name__)


def _format_briefings(pages: list[dict]) -> str:
    """Combine the page list into text for the Claude prompt.

    Each page body is wrapped in an untrusted-context block because the
    page text is prior LLM output that may itself have ingested
    attacker-controlled news content (indirect prompt injection).
    """
    return "\n\n---\n\n".join(
        f"### {p['date']} — {p['title']}\n\n"
        f"{wrap_untrusted(p['text'], label='previous_briefing')}"
        for p in pages
    )


def week_label() -> str:
    """Return this week's range label (e.g. 2026-04-19〜2026-04-25)."""
    today = date.today()
    start = today - timedelta(days=6)
    return f"{start.strftime('%Y-%m-%d')}〜{today.strftime('%Y-%m-%d')}"


def generate_weekly_summary(pages: list[dict]) -> str:
    """Generate and return the weekly summary from the last 7 days of pages."""
    if not pages:
        raise ValueError("no pages found for weekly summary generation")

    prompt = render("weekly_summary", briefings=_format_briefings(pages), week_label=week_label())

    logger.info("generating weekly summary (model=%s, pages=%d)...", get_model(), len(pages))
    return run_claude(prompt, "週次サマリー生成", TIMEOUT_WEEKLY_SUMMARY)
