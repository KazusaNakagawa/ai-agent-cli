"""Assemble the final Markdown by joining the caveat header and the generated body."""

from __future__ import annotations

from datetime import datetime

from .validate import UrlValidation


def compose_briefing_md(
    body: str,
    *,
    model: str,
    generated_at: datetime,
    search_enabled: bool = True,
    url_validation: UrlValidation | None = None,
    prefetch_summary: str | None = None,
    article_summary: str | None = None,
) -> str:
    """Join the caveat header and the body with `---`.

    If `url_validation` is given, append "URL 検証: verified/total" to the caveat.
    If `prefetch_summary` is given, append the "Brave hits: ..." count line.
    If `article_summary` is given, append the "記事本文: ..." fetch-status line (#151).
    All are for operational transparency, to back up `-` source cells and vague statements.
    """
    search_line = (
        "> - Web 検索: Brave Search (pre-fetch)\n"
        if search_enabled
        else "> - Web 検索: 無効（BRAVE_API_KEY 未設定）\n"
    )
    summary_line = ""
    if prefetch_summary:
        summary_line = f"> - Brave hits: {prefetch_summary}\n"
    article_line = ""
    if article_summary:
        article_line = f"> - 記事本文: {article_summary}\n"
    validation_line = ""
    if url_validation is not None:
        validation_line = (
            f"> - URL 検証: {url_validation.verified}/{url_validation.total} "
            f"が pre-fetch 由来 (捏造 {url_validation.fabricated} 件は `<URL未検証>` に置換)\n"
        )
    head = (
        "> **※ ローカル LLM 生成（実験版）**\n"
        f"> - model: {model}\n"
        f"{search_line}"
        f"{summary_line}"
        f"{article_line}"
        f"{validation_line}"
        f"> - generated_at: {generated_at.isoformat(timespec='seconds')}\n"
    )
    return f"{head}\n---\n\n{body.rstrip()}\n"
