"""ローカル LLM 用ブリーフィング生成。プロンプト組立・検索 pre-fetch・Ollama 呼び出し・MD 組成。

設計方針:
- #144 pre-fetch 化: qwen2.5:14b の tool-calling は不安定 (8 銘柄中 2 銘柄しか検索しない)
  ため Python 側で必ず全件 web_search し、プロンプトに注入する。tool 経路は廃止。
- セクション分割 (#後続): 9 セクションを 1 回の chat() で生成させると attention が
  分散し、保有銘柄テーブルなどで URL 捏造が頻発した。トップニュース / 地政学+イベント /
  示唆 の各段に分けて、各段で渡す web_context をそのセクション分だけに絞ることで、
  引用追従を安定させる。保有銘柄テーブルは portfolio.py の構造化出力経路 (#152) に分離。
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
# Brave の count 上限は 10 (クライアント側で clamp)。現状の PER_* 最大は 3 なので
# 3+3=6 で枠内だが、PER_* を増やす場合は 10 を超えないよう注意。
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
        # CNBC のクオート/銘柄ページ (/quotes/SYMBOL)。記事 (/YYYY/MM/DD/...) は残す。
        r"cnbc\.com/quotes/",
        # Amazon は商品詳細ページ (/dp/, /gp/product/ — 商品名スラッグ付きも可)
        # のみ除外。記事系ページまで落とさないようドメイン全体は対象にしない。
        r"amazon\.(com|co\.jp)/(.+/)?(gp/product|dp)/",
        # 株価予想・アナリストレーティングの集約ページ (#158)。常設の目標株価/
        # 予想ページで当日の事実を含まず、投資判断価値が低い。各サイトの記事系
        # (/originals/, /news/ 等) は残すため、予想ページのパスに絞って除外する。
        r"marketbeat\.com/stocks/",
        r"simplywall\.st/stocks/",
        r"tipranks\.com/stocks/",
        r"wallstreetzen\.com/stocks/",
        r"cnn\.com/markets/stocks/",
        # 13F 保有変動の自動量産スパム & レーティング/煽り系 (実機検証で表を汚した)。
        # 記事本文に当日の一次情報がほぼ無いためドメインごと除外。fool.com /
        # 247wallst は良質記事も混じるため対象にしない。
        r"americanbankingnews\.com",
        r"dailypolitical\.com",
        r"themarketsdaily\.com",
        r"weissratings\.com",
        r"timothysykes\.com",
        r"stockstotrade\.com",
        # クオート/ライブ株価の索引ページ & バリュエーション予想サイト (#176)。
        # indmoney は銘柄のライブ株価ページ、trefis は予想/バリュエーション記事。
        r"indmoney\.com/us-stocks/",
        r"trefis\.com/stock/",
    )
]


def _is_index_page(url: str) -> bool:
    return any(p.search(url) for p in _INDEX_PAGE_URL_PATTERNS)


def _url_has_no_spaces(url: str) -> bool:
    """URL にスペースが含まれないか確認（空白チェックのみ）。Markdown リンク崩壊防止 (#181)。"""
    return " " not in url


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
    kept = []
    n_index = n_malformed = 0
    for r in hits:
        if _is_index_page(r.url):
            n_index += 1
        elif not _url_has_no_spaces(r.url):
            n_malformed += 1
        else:
            kept.append(r)
    if n_index:
        logger.info("[prefetch] %r: 索引ページ %d 件を除外", query, n_index)
    if n_malformed:
        logger.info("[prefetch] %r: 不正URL(スペース含む) %d 件を除外", query, n_malformed)
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
        # 本文抜粋 (#151)。enrich_with_article_text が埋めた上位ヒットのみ持つ。
        # スニペットより具体的な事実 (数値・日付・固有名詞) の唯一の供給源。
        if r.content:
            out.append(f"    - 本文抜粋: {r.content}")
    return "\n".join(out)


def render_macro_block(ctx: PrefetchedContext) -> str:
    """マクロ・市場全体だけを抜き出した検索結果ブロック。"""
    return "### マクロ・市場全体\n" + _format_results(ctx.macro)


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


def ensure_geo_topics_covered(body: str, ctx: PrefetchedContext) -> str:
    """設定済みの地政学トピックがモデル出力から黙って抜け落ちるのを防ぐ安全網 (#175)。

    qwen2.5:14b は「投資チャネルで選別」指示の下で、原油チャネル直結の中東情勢など
    投資影響の大きいトピックまで省略することがある。body にトピック名が現れない
    場合、`### {topic}` 見出しと pre-fetch のリンクを末尾に補完し、最低限トピックと
    出典が残るようにする (要約はモデルが省略した旨を明示)。
    """
    if not ctx.geo_by_topic:
        return body
    # 見出し `### {topic}` の有無で判定する。素朴な部分一致だと URL や他トピック名の
    # 一部に含まれた場合に誤って「カバー済み」と見なす恐れがある。
    missing = [topic for topic in ctx.geo_by_topic if f"### {topic}" not in body]
    if not missing:
        return body
    parts = [body.rstrip(), ""]
    for topic in missing:
        parts.append(f"### {topic}")
        hits = ctx.geo_by_topic[topic]
        if hits:
            parts.append("（モデルが要約を省略 — 以下の検索結果を参照）")
            parts.extend(f"- [{r.title}]({r.url})" for r in hits)
        else:
            parts.append("（検索でも確認できず）")
        parts.append("")
    return "\n".join(parts).rstrip()


def build_section_topnews_prompt(
    cfg: BriefingConfig, *, ctx: PrefetchedContext, today: str
) -> str:
    """トップニュースの生成プロンプト。

    cfg を受けるのは「各ニュースの保有銘柄 ($tickers) への影響」を因果 3 行の
    一部として必ず判定させるため (#159)。出典は macro ブロックのみで、銘柄別・
    地政学のヒットはこの段では渡さない。
    """
    tickers = join_safe(cfg.portfolio.tickers, sep=", ")
    return render(
        "local_section_topnews",
        today=today,
        tickers=tickers,
        web_context=render_macro_block(ctx),
    )


def build_section_sector_prompt(
    cfg: BriefingConfig, *, prior_text: str, today: str
) -> str:
    """トップニュース本文から波及セクターを抽出し保有銘柄へ接続するプロンプト (#162)。

    世界 → セクター → 銘柄 のナラティブの中間層。出典はトップニュース本文側に
    既出なので新しい URL は書かせない (insight と同様に prior_text を参照させる)。
    """
    tickers = join_safe(cfg.portfolio.tickers, sep=", ")
    return render(
        "local_section_sector",
        today=today,
        tickers=tickers,
        prior_text=prior_text,
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
    def chat(
        self, *, model: str, messages: list[dict], options: dict | None = None
    ) -> Any: ...


def _msg_field(msg: Any, key: str, default: Any = None) -> Any:
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


# 日本語混じりテキストの 1 token ≒ 2-3 文字。控えめに 2 で割って過大側に見積もり、
# 取りこぼしより誤警告を許容する (#150)。
_CHARS_PER_TOKEN_ESTIMATE = 2


def generate_local_briefing(
    prompt: str,
    *,
    ollama_client: _OllamaChatLike,
    model: str,
    system_prompt: str | None = None,
    options: dict | None = None,
) -> str:
    """Single-turn chat()。tool calling は廃止 (pre-fetch でコンテキストは注入済み)。

    `system_prompt` を渡したら role=system を先頭に積む。qwen2.5 系は system
    指示への追従が強いので「与えられた検索結果のみを使って書け」等の制約は
    ここに置く。

    `options` は Ollama の生成オプション (num_ctx / temperature 等)。未指定だと
    Ollama 既定の num_ctx (4096) でプロンプト末尾が黙って切り捨てられるため、
    本番経路 (cli) は必ず cfg 由来の値を渡す (#150)。
    """
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    total_chars = sum(len(m["content"]) for m in messages)
    est_tokens = total_chars // _CHARS_PER_TOKEN_ESTIMATE
    num_ctx = (options or {}).get("num_ctx")
    if num_ctx and est_tokens > num_ctx:
        logger.warning(
            "[briefing] プロンプト概算 %d tokens (%d 文字) が num_ctx=%d を超過 — "
            "末尾が切り捨てられる可能性",
            est_tokens,
            total_chars,
            num_ctx,
        )
    else:
        logger.info(
            "[briefing] プロンプト概算 %d tokens (%d 文字) / num_ctx=%s",
            est_tokens,
            total_chars,
            num_ctx if num_ctx else "(Ollama 既定)",
        )

    logger.info("[briefing] ollama.chat — 単発生成 (tools 不使用)")
    resp = ollama_client.chat(model=model, messages=messages, options=options)
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
    article_summary: str | None = None,
) -> str:
    """Caveat ヘッダと本文を `---` で連結する。

    `url_validation` を渡すと caveat に「URL 検証: verified/total」を追記する。
    `prefetch_summary` を渡すと「Brave hits: ...」の件数行を追記する。
    `article_summary` を渡すと「記事本文: ...」の取得状況行を追記する (#151)。
    いずれも `-` 出典セルや曖昧な記述の裏付けを取るための運用透明性。
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
