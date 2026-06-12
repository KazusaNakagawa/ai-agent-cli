"""保有銘柄テーブルの構造化生成 (#152)。

従来はテーブル全体を 1 回の chat() で Markdown 生成させていたが、qwen2.5:14b は
- もっともらしい URL を 50% 超の確率で捏造する
- 行をまたいで出典を取り違える (NOC 行に MSFT の記事など)
- 見出し・ヘッダ・区切り行を省略してテーブル描画を壊す

ため、銘柄ごとに 1 コールずつ Ollama の structured outputs (format=JSON schema)
で {topic, source_index} だけを出力させる。モデルは URL を一切書かず (プロンプト
にも番号付きタイトルしか渡さない)、出典は Python 側で pre-fetch の (title, url)
に解決する。値動きセルも fetch_stock_move_map の実値で埋める。捏造・混線・
テーブル崩れが構造的に起きない。
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from src.generator.prompt import render
from src.logger import get_logger

from .briefing import PrefetchedContext, _msg_field
from .search import SearchResult

logger = get_logger(__name__)

# Ollama structured outputs に渡す JSON schema。source_index は「根拠にした
# 検索結果の番号 (1 始まり)」で、該当なしは null。
PORTFOLIO_ROW_FORMAT: dict = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "source_index": {"type": ["integer", "null"]},
    },
    "required": ["topic", "source_index"],
}

# 行プロンプトに載せる本文抜粋の上限。タスクは「1 行のトピック + 出典番号」の
# 抽出なので、セクション生成用の全文 (articles.MAX_ARTICLE_CHARS=1800) は不要。
# 銘柄ごとに chat() を回すため、短くするほどレイテンシ削減が効く。
MAX_ROW_CONTENT_CHARS = 600

NO_NEWS_TOPIC = "(具体的なニュースは検索でも確認できず)"
GENERATION_ERROR_TOPIC = "(生成エラー — 構造化出力の解析に失敗)"

TABLE_HEADER = (
    "## 保有銘柄テーブル\n"
    "\n"
    "| 銘柄 | 値動き | 今日のトピック (1 行) | 出典 |\n"
    "|---|---|---|---|"
)


class _OllamaStructuredChatLike(Protocol):
    def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        options: dict | None = None,
        format: dict | None = None,
    ) -> Any: ...


def render_numbered_hits(hits: list[SearchResult]) -> str:
    """検索結果を番号付きで整形する。**URL は意図的に含めない** (#152)。

    モデルには番号で引用させ、URL への解決は Python 側で行う。URL を見せない
    ことが捏造を構造的に不可能にする要。
    """
    lines: list[str] = []
    for i, r in enumerate(hits, start=1):
        desc = r.description.strip().replace("\n", " ")
        if len(desc) > 200:
            desc = desc[:200] + "..."
        lines.append(f"{i}. {r.title} — {desc}")
        if r.content:
            content = r.content.strip().replace("\n", " ")
            if len(content) > MAX_ROW_CONTENT_CHARS:
                content = content[:MAX_ROW_CONTENT_CHARS] + "..."
            lines.append(f"   本文抜粋: {content}")
    return "\n".join(lines)


def build_row_prompt(ticker: str, hits: list[SearchResult], *, today: str) -> str:
    return render(
        "local_portfolio_row",
        today=today,
        ticker=ticker,
        numbered_hits=render_numbered_hits(hits),
    )


def _generate_row(
    ticker: str,
    hits: list[SearchResult],
    *,
    ollama_client: _OllamaStructuredChatLike,
    model: str,
    options: dict | None,
    today: str,
) -> tuple[str, int | None]:
    """(topic, source_index) を返す。解析失敗・範囲外 index は安全側に倒す。"""
    prompt = build_row_prompt(ticker, hits, today=today)
    resp = ollama_client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options=options,
        format=PORTFOLIO_ROW_FORMAT,
    )
    msg = _msg_field(resp, "message")
    if msg is None:
        msg = resp
    content = _msg_field(msg, "content", "") or ""

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("[portfolio] %s: JSON 解析失敗: %s (raw=%r)", ticker, e, content[:200])
        return GENERATION_ERROR_TOPIC, None
    if not isinstance(data, dict):
        logger.warning("[portfolio] %s: JSON が object でない: %r", ticker, content[:200])
        return GENERATION_ERROR_TOPIC, None

    topic = str(data.get("topic") or "").strip() or NO_NEWS_TOPIC
    idx = data.get("source_index")
    if not isinstance(idx, int) or isinstance(idx, bool) or not (1 <= idx <= len(hits)):
        if idx is not None:
            logger.warning(
                "[portfolio] %s: source_index=%r が範囲外 (hits=%d) — 出典なし扱い",
                ticker,
                idx,
                len(hits),
            )
        idx = None
    return topic, idx


def _sanitize_cell(text: str) -> str:
    """Markdown テーブルを壊す `|` と改行を畳む。"""
    return text.replace("|", " ").replace("\n", " ").strip()


def generate_portfolio_table(
    tickers: list[str],
    *,
    ctx: PrefetchedContext,
    moves: dict[str, str],
    ollama_client: _OllamaStructuredChatLike,
    model: str,
    options: dict | None = None,
    today: str,
) -> str:
    """全銘柄分の保有銘柄テーブルを Markdown で返す。

    検索ヒット 0 件の銘柄は LLM を呼ばずに即「確認できず」行を出す (コール節約)。
    出典セルは source_index を pre-fetch の (title, url) に解決して Python 側で
    リンク化するため、URL 捏造は起こり得ない。
    """
    rows = [TABLE_HEADER]
    for ticker in tickers:
        hits = ctx.per_ticker.get(ticker, [])
        move = _sanitize_cell(moves.get(ticker, "-")) or "-"

        if not hits:
            topic: str = NO_NEWS_TOPIC
            idx: int | None = None
        else:
            logger.info("[portfolio] %s: 行生成 (hits=%d)", ticker, len(hits))
            topic, idx = _generate_row(
                ticker,
                hits,
                ollama_client=ollama_client,
                model=model,
                options=options,
                today=today,
            )

        if idx is not None:
            src = hits[idx - 1]
            source = f"[{_sanitize_cell(src.title)}]({src.url})"
        else:
            source = "-"
        rows.append(f"| {ticker} | {move} | {_sanitize_cell(topic)} | {source} |")
    return "\n".join(rows)
