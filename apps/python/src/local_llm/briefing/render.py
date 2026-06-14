"""Markdown rendering of the pre-fetch context and model output.

Responsible for the search-result block injected into the prompt, the caveat
summary, the debug fold-out, and the Python-side listing of reference articles.
"""

from __future__ import annotations

from ..search import SearchResult
from .filters import _trim_md_link_closer, _URL_RE
from .prefetch import PrefetchedContext


def _format_results(results: list[SearchResult]) -> str:
    if not results:
        return "  - (検索ヒットなし)"
    out = []
    for r in results:
        desc = r.description.strip().replace("\n", " ")
        if len(desc) > 200:
            desc = desc[:200] + "..."
        out.append(f"  - [{r.title}]({r.url}) — {desc}")
        # Body excerpt (#151). Only top hits filled in by enrich_with_article_text have it.
        # The sole source of concrete facts (numbers, dates, proper nouns) beyond the snippet.
        if r.content:
            out.append(f"    - 本文抜粋: {r.content}")
    return "\n".join(out)


def render_macro_block(ctx: PrefetchedContext) -> str:
    """Search-result block extracting only macro / overall-market results."""
    return "### マクロ・市場全体\n" + _format_results(ctx.macro)


def render_geo_events_block(ctx: PrefetchedContext) -> str:
    """Block extracting only geopolitical topics and watch events.

    Returns an empty string if both are empty (a marker telling the prompt to omit
    the whole section).
    """
    parts: list[str] = []
    if ctx.geo_by_topic:
        parts.append("### 地政学トピック")
        for topic, results in ctx.geo_by_topic.items():
            parts.append(f"\n**{topic}**")
            parts.append(_format_results(results))
    if ctx.events_by_name:
        if parts:
            parts.append("")
        parts.append("### 監視イベント")
        for name, results in ctx.events_by_name.items():
            parts.append(f"\n**{name}**")
            parts.append(_format_results(results))
    return "\n".join(parts)


def ensure_geo_topics_covered(body: str, ctx: PrefetchedContext) -> str:
    """Safety net preventing configured geopolitical topics from silently dropping out of the model output (#175).

    Under the "filter by investment channel" instruction, qwen2.5:14b sometimes
    omits even high-impact topics such as Middle East tensions that tie directly to
    the oil channel. When a topic name does not appear in body, append a
    `### {topic}` heading and the pre-fetch links so that at least the topic and
    its sources remain (noting that the model omitted the summary).
    """
    if not ctx.geo_by_topic:
        return body
    # Judge by the presence of the `### {topic}` heading. A naive substring match
    # could wrongly count it as "covered" if it appears inside a URL or another topic name.
    missing = [topic for topic in ctx.geo_by_topic if f"### {topic}" not in body]
    if not missing:
        return body
    supplement_lines: list[str] = []
    for topic in missing:
        supplement_lines.append(f"### {topic}")
        hits = ctx.geo_by_topic[topic]
        if hits:
            supplement_lines.append("（モデルが要約を省略 — 以下の検索結果を参照）")
            supplement_lines.extend(f"- [{r.title}]({r.url})" for r in hits)
        else:
            supplement_lines.append("（検索でも確認できず）")
        supplement_lines.append("")
    supplement = "\n".join(supplement_lines).rstrip()
    # If there is a watch-events section, insert it just before that (#006 regression).
    events_marker = "\n## 監視イベント"
    if events_marker in body:
        idx = body.index(events_marker)
        return body[:idx].rstrip() + "\n\n" + supplement + "\n" + body[idx:]
    return body.rstrip() + "\n\n" + supplement


def summarize_prefetch_hits(ctx: PrefetchedContext) -> str:
    """Format how many hits Brave Search returned into a single line (for the caveat).

    For tickers whose source cell in `local_*.md` is `-`, this lets the operator
    immediately tell whether "pre-fetch got nothing" vs. "it got results but the
    LLM did not use them". The `tickers=[PLTR:3, CBRS:0, ...]` form makes the
    0-hit cases visible at a glance.
    """
    parts: list[str] = [f"macro={len(ctx.macro)}"]
    if ctx.per_ticker:
        body = ", ".join(f"{t}:{len(h)}" for t, h in ctx.per_ticker.items())
        parts.append(f"tickers=[{body}]")
    if ctx.geo_by_topic:
        body = ", ".join(f"{t}:{len(h)}" for t, h in ctx.geo_by_topic.items())
        parts.append(f"geo=[{body}]")
    if ctx.events_by_name:
        body = ", ".join(f"{n}:{len(h)}" for n, h in ctx.events_by_name.items())
        parts.append(f"events=[{body}]")
    return " / ".join(parts)


def render_prefetch_debug_block(ctx: PrefetchedContext) -> str:
    """Return the raw pre-fetch URL/title list as a `<details>` fold-out.

    The caveat's count summary alone does not show "what exactly was fetched", so
    list everything at the end of the body as an expandable debug block. It folds
    in GitHub / GitLab Markdown and expands plainly in Notion (large, but does not
    break).
    """

    def _list(results: list[SearchResult]) -> list[str]:
        if not results:
            return ["- (検索ヒットなし)"]
        return [f"- [{r.title}]({r.url})" for r in results]

    lines: list[str] = []
    lines.append("<details><summary>Pre-fetch raw (debug)</summary>")
    lines.append("")
    lines.append("### マクロ・市場全体")
    lines.extend(_list(ctx.macro))

    if ctx.per_ticker:
        lines.append("")
        lines.append("### 銘柄別")
        for ticker, results in ctx.per_ticker.items():
            lines.append("")
            lines.append(f"**{ticker} ({len(results)} 件)**")
            lines.extend(_list(results))

    if ctx.geo_by_topic:
        lines.append("")
        lines.append("### 地政学")
        for topic, results in ctx.geo_by_topic.items():
            lines.append("")
            lines.append(f"**{topic} ({len(results)} 件)**")
            lines.extend(_list(results))

    if ctx.events_by_name:
        lines.append("")
        lines.append("### 監視イベント")
        for name, results in ctx.events_by_name.items():
            lines.append("")
            lines.append(f"**{name} ({len(results)} 件)**")
            lines.extend(_list(results))

    lines.append("")
    lines.append("</details>")
    return "\n".join(lines)


def collect_references(ctx: PrefetchedContext, body: str) -> str:
    """List the allowed URLs that actually appear in the A-C body under `## 参考記事`.

    Letting the model write the references causes frequent duplicates,
    fabrication, and ordering breakage (qwen2.5:14b's limit on following URL
    citations). Extracting URLs from the body on the Python side and matching them
    against the pre-fetch (title, url) to make Markdown links is far more reliable.
    """
    found_raw = _URL_RE.findall(body)
    if not found_raw:
        return "## 参考記事\n- (本文中に引用 URL なし)"

    url_to_title: dict[str, str] = {}
    for r in ctx.macro:
        url_to_title.setdefault(r.url, r.title)
    for hits in ctx.per_ticker.values():
        for r in hits:
            url_to_title.setdefault(r.url, r.title)
    for hits in ctx.geo_by_topic.values():
        for r in hits:
            url_to_title.setdefault(r.url, r.title)
    for hits in ctx.events_by_name.values():
        for r in hits:
            url_to_title.setdefault(r.url, r.title)

    lines = ["## 参考記事"]
    seen: set[str] = set()
    for url in (_trim_md_link_closer(u) for u in found_raw):
        if url in seen:
            continue
        seen.add(url)
        title = url_to_title.get(url)
        if title:
            lines.append(f"- [{title}]({url})")
    if len(lines) == 1:
        lines.append("- (引用 URL は全て pre-fetch 外 — `<URL未検証>` に置換済み)")
    return "\n".join(lines)
