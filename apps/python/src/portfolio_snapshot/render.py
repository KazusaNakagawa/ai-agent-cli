"""Markdown rendering, including the allocation-rule verdicts.

Reads a ``Snapshot`` and returns text; it never fetches or computes valuations.
"""
from __future__ import annotations

from .models import (
    HIGH_RISK_BUCKET,
    INDEX_BUCKET,
    Snapshot,
    Valued,
    bucket_label,
)

# Yen-strengthening levels to price the portfolio against. Mirrors
# briefing.json's fx.scenario_rates so both surfaces tell the same story.
FX_SCENARIOS = (150, 140, 130)

# Allocation guidelines from the 2026-08-04 analyses, checked automatically so a
# snapshot answers "am I inside my own rules" without re-deriving them.
HIGH_RISK_BUCKET_MAX = 0.15  # the high-risk sleeve as a whole
SINGLE_HIGH_RISK_MAX = 0.05  # any single high-risk name
SINGLE_NAME_MAX = 0.15  # any single stock, above which adding deepens concentration


def _yen(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _yen_symbol(value: float | None) -> str:
    """Yen with its symbol, or a bare em dash — never a symbol with no number."""
    return "—" if value is None else f"¥{value:,.0f}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _money(value: float | None, currency: str) -> str:
    if value is None:
        return "—"
    return f"{'¥' if currency == 'JPY' else '$'}{value:,.2f}"


def _price_cell(v: Valued) -> str:
    if v.is_manual:
        return "手入力"
    if v.price is None:
        return v.error or "—"
    return _money(v.price, v.currency)


def _render_header(s: Snapshot) -> list[str]:
    lines = [
        f"# ポートフォリオ・スナップショット {s.holdings.as_of}",
        "",
        f"- USD/JPY **{s.fx:,.2f}**（{'指定値' if s.fx_is_override else 'yfinance 直近値'}）",
        f"- 株式評価額 **{_yen_symbol(s.equity_jpy)}** ／ 現金 **{_yen_symbol(s.cash_jpy)}**"
        f" ／ 総資産 **{_yen_symbol(s.total_jpy)}**",
    ]
    if s.unvalued_tickers:
        lines.append(
            f"- ⚠️ 株数または現在値が取れず集計に含めていない銘柄: {', '.join(s.unvalued_tickers)}"
        )
    if any(v.is_manual for v in s.valued) and s.holdings.source:
        lines.append(f"- ⚠️ 「手入力」の行は holdings.json 記載時点の評価額。出典: {s.holdings.source}")
    return lines


def _render_positions(s: Snapshot) -> list[str]:
    lines = [
        "",
        "## 保有一覧",
        "",
        "| 銘柄 | 口座 | 区分 | 株数 | 取得単価 | 現在値 | 評価額(円) | 損益率 | 比率 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for v in sorted(s.valued, key=lambda x: (x.value_jpy or -1), reverse=True):
        p = v.position
        label = p.ticker + (f"<br>{p.name}" if p.name else "")
        lines.append(
            f"| {label} | {p.account} | {bucket_label(p.bucket)} "
            f"| {f'{p.shares:g}' if p.shares else '—'} | {_money(p.avg_cost, v.currency)} "
            f"| {_price_cell(v)} | {_yen(v.value_jpy)} | {_pct(v.pnl_pct)} "
            f"| {_pct(s.weight(v.value_jpy))} |"
        )
    lines.append(
        f"| **現金** | - | - | - | - | - | {_yen(s.cash_jpy)} | — | {_pct(s.weight(s.cash_jpy))} |"
    )
    return lines


def _render_ticker_totals(s: Snapshot) -> list[str]:
    """Only names held in more than one account; the rest are readable above."""
    split = {t: v for t, v in s.by_ticker().items() if s.account_count(t) > 1}
    if not split:
        return []
    lines = [
        "",
        "## 口座をまたぐ銘柄の合計",
        "",
        "| 銘柄 | 評価額(円) | 比率 |",
        "|---|---:|---:|",
    ]
    for ticker, value in sorted(split.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"| {ticker} | {_yen(value)} | {_pct(s.weight(value))} |")
    return lines


def _render_fx_exposure(s: Snapshot) -> list[str]:
    """Look-through, not listing currency: a yen-quoted world index still moves
    with the yen, and that is what the scenarios below have to price."""
    foreign = s.foreign_jpy
    domestic = s.total_jpy - foreign
    lines = [
        "",
        "## 通貨エクスポージャー（ルックスルー）",
        "",
        "| 区分 | 評価額(円) | 比率 |",
        "|---|---:|---:|",
        f"| 外貨建て（主に USD） | {_yen(foreign)} | {_pct(s.weight(foreign))} |",
        f"| 円建て | {_yen(domestic)} | {_pct(s.weight(domestic))} |",
        "",
    ]
    if s.total_jpy:
        for rate in FX_SCENARIOS:
            impact = foreign * (rate / s.fx - 1) / s.total_jpy * 100
            lines.append(
                f"- USD/JPY **{rate}** まで円高が進んだ場合の総資産インパクト: **{impact:.1f}%**"
            )
    return lines


def _render_buckets(s: Snapshot) -> list[str]:
    lines = ["", "## 区分別の集中度", "", "| 区分 | 評価額(円) | 比率 |", "|---|---:|---:|"]
    for bucket, value in sorted(s.by_bucket().items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"| {bucket_label(bucket)} | {_yen(value)} | {_pct(s.weight(value))} |")
    return lines


def _render_rules(s: Snapshot) -> list[str]:
    """Pass/fail against the allocation rules earlier analyses set."""
    lines = ["", "## ルール判定", ""]
    if not s.total_jpy:
        return lines + ["- 株数が未入力のため判定できません。holdings.json を埋めてください。"]

    buckets = s.by_bucket()
    high_risk = s.weight(buckets.get(HIGH_RISK_BUCKET, 0)) or 0
    lines.append(
        f"- 高リスク枠 **{high_risk:.1f}%**（ガイド {HIGH_RISK_BUCKET_MAX:.0%} 以内）"
        f" → {'OK' if high_risk <= HIGH_RISK_BUCKET_MAX * 100 else '超過'}"
    )
    for v in s.valued:
        if v.position.bucket == HIGH_RISK_BUCKET and v.value_jpy:
            w = s.weight(v.value_jpy) or 0
            lines.append(
                f"  - {v.position.ticker} {w:.1f}%（1銘柄 {SINGLE_HIGH_RISK_MAX:.0%} 以内）"
                f" → {'OK' if w <= SINGLE_HIGH_RISK_MAX * 100 else '超過'}"
            )

    # Single-name concentration, summed across accounts. Index funds are
    # diversified by construction, so the rule applies to individual names only.
    index_tickers = {
        v.position.ticker for v in s.valued if v.position.bucket == INDEX_BUCKET
    }
    for ticker, value in sorted(s.by_ticker().items(), key=lambda kv: kv[1], reverse=True):
        if ticker in index_tickers:
            continue
        w = s.weight(value) or 0
        if w >= SINGLE_NAME_MAX * 100:
            lines.append(
                f"- {ticker} 比率 **{w:.1f}%**（単一銘柄 {SINGLE_NAME_MAX:.0%} 超）"
                " → 買い増しは集中を深める。見送り・比率維持が既定"
            )

    for bucket in (b for b in buckets if b not in (INDEX_BUCKET, HIGH_RISK_BUCKET)):
        w = s.weight(buckets[bucket]) or 0
        if w >= SINGLE_NAME_MAX * 100:
            lines.append(f"- {bucket_label(bucket)} 1テーマへの集中 **{w:.1f}%** → 同時に下げる部分の大きさ")

    if s.holdings.nisa_growth_remaining_jpy:
        lines.append(
            f"- NISA成長投資枠 残 **{_yen_symbol(s.holdings.nisa_growth_remaining_jpy)}**"
            "（配当のある円建て・長期保有向け）"
        )
    lines.append(f"- 現金余力 **{_yen_symbol(s.cash_jpy)}** → 分割エントリー何回分かの原資")
    return lines


def render_snapshot(s: Snapshot) -> str:
    sections = (
        _render_header(s)
        + _render_positions(s)
        + _render_ticker_totals(s)
        + _render_fx_exposure(s)
        + _render_buckets(s)
        + _render_rules(s)
        + ["", "---", "", "※ 価格は yfinance の直近値。取得単価・現金は holdings.json の入力値。"]
    )
    return "\n".join(sections) + "\n"
