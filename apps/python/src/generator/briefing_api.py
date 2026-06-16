"""Claude API briefing — cost-verification spike (#204).

Runs the daily briefing through the raw Anthropic Messages API (Sonnet 4.6, no
tools) instead of the `claude` CLI, to verify whether removing the CLI's large
agentic system-prompt/tool overhead lowers cost. Web search is supplied by
reusing the local-LLM Brave pre-fetch, so the API call needs no tools.

This is a spike, fully separate from the production CLI path
(`src/generator/briefing.py`). See
`docs/superpowers/specs/2026-06-17-briefing-api-spike-design.md`.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from src.config import BriefingConfig, load_config
from src.constants import BRIEFING_OUTPUT_DIR
from src.credentials import get_credential
from src.fetcher.stocks import fetch_stock_move_map
from src.generator.briefing import (
    build_geopolitical_context,
    build_watch_events_context,
    build_watch_sectors_context,
    join_safe,
    load_briefing_few_shot,
)
from src.generator.prompt import render
from src.logger import get_logger
from src.usage_logger import log_usage
from src.local_llm.articles import enrich_with_article_text
from src.local_llm.briefing import prefetch_briefing_context
from src.local_llm.search import BraveSearchClient, SearchResult

logger = get_logger(__name__)

SONNET_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
SYSTEM_PROMPT = (
    "あなたは投資家向けの世界情勢アナリストです。必ず日本語で、与えられた取得済み記事だけを"
    "根拠に、捏造せず簡潔に記述してください。"
)

# Sonnet 4.6 pricing, USD per token (per-Mtok: input 3 / output 15 /
# cache-write 3.75 / cache-read 0.30).
_PRICE_INPUT = 3.0 / 1_000_000
_PRICE_OUTPUT = 15.0 / 1_000_000
_PRICE_CACHE_WRITE = 3.75 / 1_000_000
_PRICE_CACHE_READ = 0.30 / 1_000_000


def compute_cost_usd(usage: dict) -> float:
    """Cost of one Sonnet call from its token usage breakdown."""
    return (
        usage.get("input_tokens", 0) * _PRICE_INPUT
        + usage.get("output_tokens", 0) * _PRICE_OUTPUT
        + usage.get("cache_creation_input_tokens", 0) * _PRICE_CACHE_WRITE
        + usage.get("cache_read_input_tokens", 0) * _PRICE_CACHE_READ
    )


def _render_hits(label: str, hits: list[SearchResult]) -> str:
    lines = [f"### {label}"]
    for h in hits:
        body = h.content or h.description
        lines.append(f"- [{h.title}]({h.url})\n  {body}")
    return "\n".join(lines)


def build_context_block(ctx) -> str:
    """Flatten the pre-fetched context into a plain-text block for the prompt."""
    blocks: list[str] = []
    if ctx.macro:
        blocks.append(_render_hits("マクロ", ctx.macro))
    for ticker, hits in ctx.per_ticker.items():
        if hits:
            blocks.append(_render_hits(f"銘柄: {ticker}", hits))
    for topic, hits in ctx.geo_by_topic.items():
        if hits:
            blocks.append(_render_hits(f"地政学: {topic}", hits))
    for name, hits in ctx.events_by_name.items():
        if hits:
            blocks.append(_render_hits(f"イベント: {name}", hits))
    return "\n\n".join(blocks) if blocks else "(取得済み記事なし)"


def build_api_prompts(
    *,
    themes: str,
    tickers: str,
    geopolitical: str,
    watch_events: str,
    watch_sectors: str,
    stocks: str,
    few_shot: str,
    context_block: str,
) -> tuple[str, str]:
    """Build the main + sectors prompts from the API templates (no WebSearch)."""
    main_prompt = render(
        "briefing_api",
        themes=themes,
        tickers=tickers,
        geopolitical=geopolitical,
        watch_events=watch_events,
        stocks=stocks,
        few_shot=few_shot,
        context=context_block,
    )
    sectors_prompt = render(
        "briefing_sectors_api",
        watch_sectors=watch_sectors,
        stocks=stocks,
        context=context_block,
    )
    return main_prompt, sectors_prompt


def generate_section(client, *, system: str, prompt: str) -> tuple[str, dict]:
    """Call Sonnet (no tools) for one section; return (text, usage dict)."""
    msg = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text if msg.content else ""
    u = msg.usage
    usage = {
        "input_tokens": getattr(u, "input_tokens", 0),
        "output_tokens": getattr(u, "output_tokens", 0),
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0),
    }
    return text, usage


def log_section_usage(label: str, usage: dict, *, duration_ms: int | None) -> None:
    """Record a section's usage + computed Sonnet cost under an (API) label."""
    log_usage(label, usage, compute_cost_usd(usage), duration_ms)


def _make_client():
    api_key = get_credential("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY が未設定です（Keychain か .env に設定してください）"
        )
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def run_briefing_api(config: BriefingConfig, client) -> str:
    """Generate the briefing via the API path and return the assembled markdown."""
    today = date.today().isoformat()
    tickers = join_safe(config.portfolio.tickers, sep=", ")
    themes = join_safe(config.portfolio.themes, sep=", ")

    logger.info("株価取得中...")
    moves = fetch_stock_move_map(config.portfolio.tickers)
    stocks = "\n".join(f"- {t}: {m}" for t, m in moves.items()) or "(取得なし)"

    logger.info("Brave Search pre-fetch...")
    search_client = BraveSearchClient(_require_brave_key())
    ctx = prefetch_briefing_context(config, search_client=search_client, today=today)
    ctx = enrich_with_article_text(ctx)
    context_block = build_context_block(ctx)

    main_prompt, sectors_prompt = build_api_prompts(
        themes=themes,
        tickers=tickers,
        geopolitical=build_geopolitical_context(config),
        watch_events=build_watch_events_context(config),
        watch_sectors=build_watch_sectors_context(config),
        stocks=stocks,
        few_shot=load_briefing_few_shot(),
        context_block=context_block,
    )

    main_text = _gen_and_log(client, "メイン分析(API)", main_prompt)
    sectors_text = _gen_and_log(client, "セクタースイープ(API)", sectors_prompt)

    return f"{main_text}\n\n---\n\n{sectors_text}\n"


def _gen_and_log(client, label: str, prompt: str) -> str:
    t0 = datetime.now()
    text, usage = generate_section(client, system=SYSTEM_PROMPT, prompt=prompt)
    dt_ms = int((datetime.now() - t0).total_seconds() * 1000)
    log_section_usage(label, usage, duration_ms=dt_ms)
    logger.info("[section] %s 生成完了 (%d 文字)", label, len(text))
    return text


def _require_brave_key() -> str:
    import os

    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        raise SystemExit("BRAVE_API_KEY が未設定です（.env に設定してください）")
    return key


def main(argv: list[str] | None = None) -> int:
    logger.info("=== Claude API ブリーフィング（検証スパイク）開始 ===")
    config = load_config()
    client = _make_client()
    md = run_briefing_api(config, client)

    today = date.today().isoformat()
    BRIEFING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(BRIEFING_OUTPUT_DIR) / f"briefing_api_{today}.md"
    out_path.write_text(md, encoding="utf-8")
    logger.info("保存完了: %s", out_path)
    logger.info("=== Claude API ブリーフィング終了 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
