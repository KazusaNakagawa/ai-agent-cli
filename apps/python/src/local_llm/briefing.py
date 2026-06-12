"""ローカル LLM 用ブリーフィング生成。プロンプト組立・検索 pre-fetch・Ollama 呼び出し・MD 組成。

設計方針:
- #144 pre-fetch 化: qwen2.5:14b の tool-calling は不安定 (8 銘柄中 2 銘柄しか検索しない)
  ため Python 側で必ず全件 web_search し、プロンプトに注入する。tool 経路は廃止。
- セクション分割 (#後続): 9 セクションを 1 回の chat() で生成させると attention が
  分散し、保有銘柄テーブルなどで URL 捏造が頻発した。トップニュース / 保有銘柄 /
  地政学+イベント / 示唆 の 4 段に分けて、各段で渡す web_context をそのセクション分
  だけに絞ることで、引用追従を安定させる。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.config import BriefingConfig
from src.generator.briefing import join_safe
from src.generator.prompt import render
from src.logger import get_logger

from .search import BraveSearchClient, BraveSearchError, SearchResult

logger = get_logger(__name__)


PER_TICKER_RESULTS = 3
PER_MACRO_RESULTS = 3
PER_GEO_RESULTS = 2
PER_EVENT_RESULTS = 2

# Brave の鮮度フィルタ。日次ブリーフィングなので直近 1 週間に絞る (#153)。
PREFETCH_FRESHNESS = "pw"
# 索引ページフィルタで間引かれる分を見込んだ over-fetch の上乗せ件数。
OVERFETCH_EXTRA = 3

# ニュース本文ではない常設の銘柄索引/クオートページ。スニペットに当日の事実が
# 含まれず、プロンプトを汚すだけなので注入前に間引く (#153)。
_INDEX_PAGE_URL_PATTERNS = [
    re.compile(p)
    for p in (
        r"finance\.yahoo\.com/quote/",
        r"robinhood\.com/.*/stocks/",
        r"google\.com/finance",
        r"investing\.com/equities/",
        r"stockanalysis\.com/stocks/",
        r"seekingalpha\.com/symbol/",
        r"amazon\.(com|co\.jp)/",
    )
]


def _is_index_page(url: str) -> bool:
    return any(p.search(url) for p in _INDEX_PAGE_URL_PATTERNS)


@dataclass(frozen=True)
class PrefetchedContext:
    """Pre-fetched web_search のまとめ。プロンプトへの注入用。

    geo_by_topic / events_by_name は briefing.json の全エントリを 1 件ずつ
    クエリした結果。Claude 経路に対して網羅性が低かった点 (geo は先頭 1 件のみ、
    events は未取得) を補うため #144 以降に複数化した。
    """

    macro: list[SearchResult]
    per_ticker: dict[str, list[SearchResult]]
    geo_by_topic: dict[str, list[SearchResult]]
    events_by_name: dict[str, list[SearchResult]]

    @property
    def allowed_urls(self) -> set[str]:
        """URL バリデーション用ホワイトリスト。pre-fetch で取得した URL の全集合。"""
        urls: set[str] = set()
        for r in self.macro:
            urls.add(r.url)
        for hits in self.per_ticker.values():
            for r in hits:
                urls.add(r.url)
        for hits in self.geo_by_topic.values():
            for r in hits:
                urls.add(r.url)
        for hits in self.events_by_name.values():
            for r in hits:
                urls.add(r.url)
        return urls


def _safe_search(
    client: BraveSearchClient, query: str, count: int
) -> list[SearchResult]:
    """freshness=pw + 索引ページフィルタ付きの web_search (#153)。

    フィルタで間引かれても count 件残るよう OVERFETCH_EXTRA 件多めに取り、
    フィルタ後に count 件へ切り詰める。失敗は空リスト (他クエリは継続)。
    """
    try:
        hits = client.search(
            query, count=count + OVERFETCH_EXTRA, freshness=PREFETCH_FRESHNESS
        )
    except BraveSearchError as e:
        logger.warning("[prefetch] web_search failed for %r: %s", query, e)
        return []
    kept = [r for r in hits if not _is_index_page(r.url)]
    dropped = len(hits) - len(kept)
    if dropped:
        logger.info("[prefetch] %r: 索引ページ %d 件を除外", query, dropped)
    return kept[:count]


def prefetch_briefing_context(
    cfg: BriefingConfig,
    *,
    search_client: BraveSearchClient,
    today: str,
) -> PrefetchedContext:
    """マクロ + 全銘柄 + 全 conflicts + 全 watch_events を確実に web_search する。

    モデルに tool calling を任せると 8 銘柄中 2 銘柄しか検索しないなどの抜けが
    出るので、Python 側で網羅性を担保する。各クエリは Brave Free プランで安全な
    回数 (上限 1 QPS, 月 2000) に収めている。日次のクエリ数は ``1 + len(tickers)
    + len(conflicts) + len(events)`` 程度で、典型的な briefing.json (10 銘柄 + 5
    conflicts + 5 events) なら 21 クエリ/日 = 630/月 で枠内に収まる。
    """
    macro = _safe_search(search_client, f"stock market news {today}", PER_MACRO_RESULTS)
    logger.info("[prefetch] macro hits=%d", len(macro))

    per_ticker: dict[str, list[SearchResult]] = {}
    for ticker in cfg.portfolio.tickers:
        # クエリに日付を明示すると Yahoo Finance / Robinhood のティッカー index
        # ページ (汎用 SEO 上位) ではなく当日の市場記事がヒットしやすい。
        hits = _safe_search(
            search_client, f"{ticker} stock news {today}", PER_TICKER_RESULTS
        )
        per_ticker[ticker] = hits
        logger.info("[prefetch] ticker=%s hits=%d", ticker, len(hits))

    geo_by_topic: dict[str, list[SearchResult]] = {}
    for conflict in getattr(cfg.geopolitical, "conflicts", None) or []:
        name = getattr(conflict, "name", None) or ""
        if not name:
            continue
        # 日本語トピック名のままだと常設のトピック索引ページや書籍ページが上位に
        # 来る。briefing.json に query_en があれば英語ニュースクエリを使う (#153)。
        query_en = getattr(conflict, "query_en", None) or ""
        query = f"{query_en} latest news" if query_en else f"{name} today"
        hits = _safe_search(search_client, query, PER_GEO_RESULTS)
        geo_by_topic[name] = hits
        logger.info("[prefetch] geo topic=%r query=%r hits=%d", name, query, len(hits))

    events_by_name: dict[str, list[SearchResult]] = {}
    for event in getattr(cfg, "watch_events", None) or []:
        name = getattr(event, "name", None) or ""
        if not name:
            continue
        trigger = getattr(event, "trigger", None) or ""
        query = f"{name} {trigger}".strip() if trigger else f"{name} news"
        hits = _safe_search(search_client, query, PER_EVENT_RESULTS)
        events_by_name[name] = hits
        logger.info("[prefetch] event=%r hits=%d", name, len(hits))

    return PrefetchedContext(
        macro=macro,
        per_ticker=per_ticker,
        geo_by_topic=geo_by_topic,
        events_by_name=events_by_name,
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


def render_macro_block(ctx: PrefetchedContext) -> str:
    """マクロ・市場全体だけを抜き出した検索結果ブロック。"""
    return "### マクロ・市場全体\n" + _format_results(ctx.macro)


def render_portfolio_block(ctx: PrefetchedContext) -> str:
    """銘柄別検索結果だけを抜き出したブロック。"""
    parts: list[str] = ["### 銘柄別検索結果"]
    for ticker, results in ctx.per_ticker.items():
        parts.append(f"\n**{ticker}**")
        parts.append(_format_results(results))
    return "\n".join(parts)


def render_geo_events_block(ctx: PrefetchedContext) -> str:
    """地政学トピックと監視イベントだけを抜き出したブロック。

    両方とも空なら空文字を返す (プロンプトでセクションを丸ごと省略させる目印)。
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


def build_section_topnews_prompt(ctx: PrefetchedContext, *, today: str) -> str:
    return render(
        "local_section_topnews",
        today=today,
        web_context=render_macro_block(ctx),
    )


def build_section_portfolio_prompt(
    cfg: BriefingConfig, *, stocks: str, today: str, ctx: PrefetchedContext
) -> str:
    tickers = join_safe(cfg.portfolio.tickers, sep=", ")
    return render(
        "local_section_portfolio",
        today=today,
        tickers=tickers,
        stocks=stocks,
        web_context=render_portfolio_block(ctx),
    )


def build_section_geo_events_prompt(
    cfg: BriefingConfig, *, ctx: PrefetchedContext, today: str
) -> str:
    """地政学+イベントの生成プロンプト。

    cfg を受けるのは「保有銘柄 ($tickers) への影響あり/なしを必ず判定せよ」と
    いう指示を出すため。qwen2.5:14b は cfg なしだと全トピック「保有銘柄に影響なし」
    で済ませる傾向がある。
    """
    tickers = join_safe(cfg.portfolio.tickers, sep=", ")
    return render(
        "local_section_geo_events",
        today=today,
        tickers=tickers,
        web_context=render_geo_events_block(ctx),
    )


def build_section_insight_prompt(
    cfg: BriefingConfig, *, prior_text: str, today: str
) -> str:
    """A-C の本文を踏まえた「自分への示唆」生成用プロンプト。

    示唆セクションは URL 引用不要 (system prompt でも明示) なので web_context は
    渡さない。代わりに 1-3 段の本文要約を `prior_text` に流し込んでモデルに参照
    させる。
    """
    themes = join_safe(cfg.portfolio.themes, sep=", ")
    return render(
        "local_section_insight",
        today=today,
        themes=themes,
        prior_text=prior_text,
    )


def summarize_prefetch_hits(ctx: PrefetchedContext) -> str:
    """Brave Search で何件取れたかを 1 行に整形 (caveat 用)。

    `local_*.md` の出典セルが `-` になっている銘柄について、運用者が「pre-fetch
    で取れていないのか / 取れたが LLM が活用しなかったのか」を即判定できるよう
    にする。`tickers=[PLTR:3, CBRS:0, ...]` の形式で 0 件かどうかが目視できる。
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
    """pre-fetch の生 URL/タイトル一覧を `<details>` 折りたたみで返す。

    caveat の件数サマリだけでは「具体的に何を取ってきたか」が分からないので、
    本文末尾に「展開可能なデバッグブロック」として全件掲載する。GitHub /
    GitLab Markdown では折りたたみ、Notion ではプレーンに展開される (大量だ
    が崩れはしない)。
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


_PORTFOLIO_TABLE_PREAMBLE = (
    "## 保有銘柄テーブル\n"
    "\n"
    "| 銘柄 | 値動き | 今日のトピック (1 行) | 出典 |\n"
    "|---|---|---|---|"
)


def ensure_portfolio_table_header(body: str) -> str:
    """qwen2.5:14b は portfolio セクションで見出し + ヘッダ行 + 区切り行を省略しがち。

    本文がデータ行 (`| PLTR | ↓0.9% | ... |`) だけになると Markdown としては
    テーブル描画されない (区切り行がないため)。データ行があるのに区切り行が
    無い場合は見出し + ヘッダ + 区切り行を前置して描画を救う。プロンプト側でも
    強く指示しているが、後処理で確実に直すための保険。
    """
    if "|---" in body:
        return body
    lines = body.splitlines()
    has_data_row = any(line.lstrip().startswith("|") for line in lines)
    if not has_data_row:
        return body
    header_line = _PORTFOLIO_TABLE_PREAMBLE.splitlines()[2]
    divider_line = _PORTFOLIO_TABLE_PREAMBLE.splitlines()[3]
    if any(line.strip() == header_line for line in lines):
        return body.replace(header_line, f"{header_line}\n{divider_line}", 1)
    return f"{_PORTFOLIO_TABLE_PREAMBLE}\n{body.lstrip()}"


def collect_references(ctx: PrefetchedContext, body: str) -> str:
    """A-C の本文に実際に登場した allowed URL を `## 参考記事` として列挙する。

    モデルに参考記事を書かせると重複・捏造・順序崩れが頻発する (qwen2.5:14b の
    URL 引用追従限界)。Python 側で本文から URL を抜き、pre-fetch の (title, url)
    と突き合わせて Markdown リンク化する方がはるかに信頼できる。
    """
    found = _URL_RE.findall(body)
    if not found:
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
    for url in found:
        if url in seen:
            continue
        seen.add(url)
        title = url_to_title.get(url)
        if title:
            lines.append(f"- [{title}]({url})")
    if len(lines) == 1:
        lines.append("- (引用 URL は全て pre-fetch 外 — `<URL未検証>` に置換済み)")
    return "\n".join(lines)


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
    prefetch_summary: str | None = None,
) -> str:
    """Caveat ヘッダと本文を `---` で連結する。

    `url_validation` を渡すと caveat に「URL 検証: verified/total」を追記する。
    `prefetch_summary` を渡すと「Brave hits: ...」の件数行を追記する。両方とも
    `-` 出典セルの裏付けを取るための運用透明性。
    """
    search_line = (
        "> - Web 検索: Brave Search (pre-fetch)\n"
        if search_enabled
        else "> - Web 検索: 無効（BRAVE_API_KEY 未設定）\n"
    )
    summary_line = ""
    if prefetch_summary:
        summary_line = f"> - Brave hits: {prefetch_summary}\n"
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
        f"{validation_line}"
        f"> - generated_at: {generated_at.isoformat(timespec='seconds')}\n"
    )
    return f"{head}\n---\n\n{body.rstrip()}\n"
