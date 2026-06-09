"""ローカル LLM 用ブリーフィング生成。プロンプト組立・検索 pre-fetch・Ollama 呼び出し・MD 組成。

設計方針 (#144 pre-fetch 化):
- qwen2.5:14b 程度の tool-calling 追従は不安定 (実測で 8 銘柄中 2 銘柄しか検索しなかった)。
- CLI 側で全銘柄 + マクロ + 地政学 1 件の web_search を確実に実行してプロンプトに注入する。
- モデルは検索結果を整形して文章にする責務だけ持つ。tool 経路は廃止。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.config import BriefingConfig
from src.generator.briefing import (
    build_geopolitical_context,
    build_watch_events_context,
    join_safe,
)
from src.generator.prompt import render
from src.logger import get_logger

from .search import BraveSearchClient, BraveSearchError, SearchResult

logger = get_logger(__name__)


PER_TICKER_RESULTS = 2
PER_MACRO_RESULTS = 3
PER_GEO_RESULTS = 2


@dataclass(frozen=True)
class PrefetchedContext:
    """Pre-fetched web_search のまとめ。プロンプトへの注入用。"""

    macro: list[SearchResult]
    per_ticker: dict[str, list[SearchResult]]
    geo_topic: str | None
    geo_results: list[SearchResult]

    @property
    def allowed_urls(self) -> set[str]:
        """URL バリデーション用ホワイトリスト。pre-fetch で取得した URL の全集合。"""
        urls: set[str] = set()
        for r in self.macro:
            urls.add(r.url)
        for hits in self.per_ticker.values():
            for r in hits:
                urls.add(r.url)
        for r in self.geo_results:
            urls.add(r.url)
        return urls


def _pick_geo_topic(cfg: BriefingConfig) -> str | None:
    """briefing.json の geopolitical.conflicts から 1 トピックを選ぶ。

    保有銘柄に紐づく可能性が高そうな順に先頭から選ぶだけ。複雑な相関分析はせず、
    pre-fetch のクエリ材料を 1 つ取れれば十分。
    """
    conflicts = getattr(cfg.geopolitical, "conflicts", None) or []
    if not conflicts:
        return None
    return getattr(conflicts[0], "name", None) or None


def _safe_search(
    client: BraveSearchClient, query: str, count: int
) -> list[SearchResult]:
    try:
        return client.search(query, count=count)
    except BraveSearchError as e:
        logger.warning("[prefetch] web_search failed for %r: %s", query, e)
        return []


def prefetch_briefing_context(
    cfg: BriefingConfig,
    *,
    search_client: BraveSearchClient,
    today: str,
) -> PrefetchedContext:
    """全銘柄 + マクロ + 地政学 1 件を確実に web_search する。

    モデルに tool calling を任せると 8 銘柄中 2 銘柄しか検索しないなどの抜けが
    出るので、Python 側で網羅性を担保する。各クエリは Brave Free プランで安全な
    回数 (上限 1 QPS, 月 2000) に収めている。
    """
    macro = _safe_search(search_client, f"stock market news {today}", PER_MACRO_RESULTS)
    logger.info("[prefetch] macro hits=%d", len(macro))

    per_ticker: dict[str, list[SearchResult]] = {}
    for ticker in cfg.portfolio.tickers:
        hits = _safe_search(
            search_client, f"{ticker} stock news today", PER_TICKER_RESULTS
        )
        per_ticker[ticker] = hits
        logger.info("[prefetch] ticker=%s hits=%d", ticker, len(hits))

    geo_topic = _pick_geo_topic(cfg)
    geo_results: list[SearchResult] = []
    if geo_topic:
        geo_results = _safe_search(search_client, f"{geo_topic} today", PER_GEO_RESULTS)
        logger.info(
            "[prefetch] geo topic=%r hits=%d", geo_topic, len(geo_results)
        )

    return PrefetchedContext(
        macro=macro,
        per_ticker=per_ticker,
        geo_topic=geo_topic,
        geo_results=geo_results,
    )


def _format_results(results: list[SearchResult]) -> str:
    if not results:
        return "  - (検索ヒットなし)"
    out = []
    for r in results:
        desc = r.description.strip().replace("\n", " ")
        if len(desc) > 200:
            desc = desc[:200] + "..."
        out.append(f"  - [{r.title}]({r.url}) — {desc}")
    return "\n".join(out)


def render_web_context_block(ctx: PrefetchedContext) -> str:
    """PrefetchedContext を Markdown ブロックに整形してプロンプトに埋め込む。"""
    parts: list[str] = []

    parts.append("### マクロ・市場全体")
    parts.append(_format_results(ctx.macro))

    parts.append("\n### 銘柄別検索結果")
    for ticker, results in ctx.per_ticker.items():
        parts.append(f"\n**{ticker}**")
        parts.append(_format_results(results))

    if ctx.geo_topic:
        parts.append(f"\n### 地政学トピック: {ctx.geo_topic}")
        parts.append(_format_results(ctx.geo_results))

    block = "\n".join(parts)
    logger.debug("[prefetch] web_context block injected into prompt:\n%s", block)
    return block


def build_local_briefing_prompt(
    cfg: BriefingConfig,
    stocks: str,
    today: str,
    *,
    web_context: str,
) -> str:
    """local_briefing.md テンプレートに入力 + 検索結果を流し込む。

    `web_context` は ``prefetch_briefing_context`` → ``render_web_context_block``
    で生成した Markdown ブロックを想定。モデルは「この情報のみを使って書け」と
    指示されており、本文中の URL は必ずこのブロックから引かれる。

    Note: watch_sectors は意図的に渡していない。Claude 経路の並列セクタースイープに
    相当する出力をローカル版では行わない方針 (#142 spec の non-goal)。
    """
    tickers = join_safe(cfg.portfolio.tickers, sep=", ")
    themes = join_safe(cfg.portfolio.themes, sep=", ")
    return render(
        "local_briefing",
        tickers=tickers,
        themes=themes,
        geopolitical=build_geopolitical_context(cfg),
        watch_events=build_watch_events_context(cfg),
        stocks=stocks,
        today=today,
        web_context=web_context,
    )


def load_local_briefing_system_prompt() -> str:
    """system role に乗せる厳格な指示。引用ルール・出力形式を集約。"""
    return render("local_briefing_system")


class _OllamaChatLike(Protocol):
    def chat(self, *, model: str, messages: list[dict]) -> Any: ...


def _msg_field(msg: Any, key: str, default: Any = None) -> Any:
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def generate_local_briefing(
    prompt: str,
    *,
    ollama_client: _OllamaChatLike,
    model: str,
    system_prompt: str | None = None,
) -> str:
    """Single-turn chat()。tool calling は廃止 (pre-fetch でコンテキストは注入済み)。

    `system_prompt` を渡したら role=system を先頭に積む。qwen2.5 系は system
    指示への追従が強いので「与えられた検索結果のみを使って書け」等の制約は
    ここに置く。
    """
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    logger.info("[briefing] ollama.chat — 単発生成 (tools 不使用)")
    resp = ollama_client.chat(model=model, messages=messages)
    msg = _msg_field(resp, "message")
    if msg is None:
        msg = resp
    content = _msg_field(msg, "content", "") or ""
    logger.info("[briefing] 生成完了 (%d 文字)", len(content))

    if content:
        print(content, flush=True)
    return content


# Markdown リンク `[title](url)` と裸の URL の両方を拾う。
# URL 部分のみキャプチャ。終端 `)` は escape 不要 (group の内部なので)。
_URL_RE = re.compile(r"https?://[^\s)\]]+")


@dataclass(frozen=True)
class UrlValidation:
    body: str  # 捏造 URL を <URL未検証> に置換した後の本文
    total: int
    fabricated: int

    @property
    def verified(self) -> int:
        return self.total - self.fabricated


def validate_urls(body: str, ctx: PrefetchedContext) -> UrlValidation:
    """Post-validate: モデル出力中の URL のうち pre-fetch 由来でないものを `<URL未検証>` に置換。

    qwen2.5:14b は pre-fetch で URL を渡しても 50% 以上の確率で Yahoo Finance /
    Robinhood の銘柄ページ等の **見た目もっともらしい URL を捏造** する。本文の
    信頼性を担保するため、Python 側でホワイトリスト照合して捏造分を可視化する。
    """
    allowed = ctx.allowed_urls
    found = _URL_RE.findall(body)
    total = len(found)
    fabricated = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal fabricated
        url = match.group(0)
        if url in allowed:
            return url
        fabricated += 1
        return "<URL未検証>"

    cleaned = _URL_RE.sub(_replace, body)
    return UrlValidation(body=cleaned, total=total, fabricated=fabricated)


def compose_briefing_md(
    body: str,
    *,
    model: str,
    generated_at: datetime,
    search_enabled: bool = True,
    url_validation: UrlValidation | None = None,
) -> str:
    """Caveat ヘッダと本文を `---` で連結する。

    `url_validation` を渡すと caveat に「URL 検証: verified/total」を追記する。
    捏造件数が 0 でなければ運用者がすぐ気付けるようにする目的。
    """
    search_line = (
        "> - Web 検索: Brave Search (pre-fetch)\n"
        if search_enabled
        else "> - Web 検索: 無効（BRAVE_API_KEY 未設定）\n"
    )
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
        f"{validation_line}"
        f"> - generated_at: {generated_at.isoformat(timespec='seconds')}\n"
    )
    return f"{head}\n---\n\n{body.rstrip()}\n"
