"""週次ブリーフィングサマリーを生成する。"""
from datetime import date, timedelta

from src.claude_runner import run_claude
from src.constants import TIMEOUT_WEEKLY_SUMMARY
from src.generator.prompt import render
from src.logger import get_logger
from src.prompt_safety import wrap_untrusted

logger = get_logger(__name__)


def _format_briefings(pages: list[dict]) -> str:
    """ページリストを Claude プロンプト用テキストにまとめる。

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
    """今週の範囲ラベルを返す（例: 2026-04-19〜2026-04-25）。"""
    today = date.today()
    start = today - timedelta(days=6)
    return f"{start.strftime('%Y-%m-%d')}〜{today.strftime('%Y-%m-%d')}"


def generate_weekly_summary(pages: list[dict]) -> str:
    """過去7日分のページリストから週次サマリーを生成して返す。"""
    if not pages:
        raise ValueError("週次サマリー生成に必要なページが見つかりませんでした")

    prompt = render("weekly_summary", briefings=_format_briefings(pages), week_label=week_label())

    logger.info("週次サマリー生成中 (対象ページ数=%d)...", len(pages))
    return run_claude(prompt, "週次サマリー生成", TIMEOUT_WEEKLY_SUMMARY)
