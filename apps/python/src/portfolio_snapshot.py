"""Portfolio snapshot — turn a holdings file into the one table every analysis needs.

Repeated position-sizing analyses stalled on the same missing input ("actual
weights and cash are unknown"), so this renders holdings + live quotes into a
single Markdown snapshot: per-position value in JPY, weight, look-through
currency exposure, bucket concentration, and pass/fail against the allocation
rules those analyses set.

Input is ``config/holdings.json`` (gitignored — see ``holdings.json.example``);
output goes to ``output/portfolio/snapshot_<date>.md``.

Usage:
    python -m src.portfolio_snapshot                 # write the snapshot file
    python -m src.portfolio_snapshot --stdout        # print instead
    python -m src.portfolio_snapshot --holdings PATH # use another holdings file
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.fetcher.stocks import StockQuote, fetch_stock_quotes
from src.logger import get_logger

logger = get_logger(__name__)

HOLDINGS_PATH = Path(__file__).parents[1] / "config" / "holdings.json"
OUTPUT_DIR = Path(__file__).parents[1] / "output" / "portfolio"

FX_SYMBOL = "JPY=X"
FX_FALLBACK = 157.0
# Yen-strengthening levels to price the portfolio against. Mirrors
# briefing.json's fx.scenario_rates so both surfaces tell the same story.
FX_SCENARIOS = (150, 140, 130)

# Bucket keys are free-form in the holdings file; these are the ones with a
# label (and, for high_risk, a rule) attached.
BUCKET_LABELS = {
    "ai_growth": "AIグロース",
    "high_risk": "高リスク枠",
    "defensive": "ディフェンシブ",
    "healthcare": "ヘルスケア",
    "defense": "防衛",
    "japan": "日本株・円建て",
    "index": "インデックス",
    "other": "その他",
}
HIGH_RISK_BUCKET = "high_risk"
INDEX_BUCKET = "index"

# Allocation guidelines from the 2026-08-04 analyses, checked automatically so a
# snapshot answers "am I inside my own rules" without re-deriving them.
HIGH_RISK_BUCKET_MAX = 0.15  # the high-risk sleeve as a whole
SINGLE_HIGH_RISK_MAX = 0.05  # any single high-risk name
SINGLE_NAME_MAX = 0.15  # any single stock, above which adding deepens concentration


# --------------------------------------------------------------------------
# Input model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Position:
    """One line of the holdings file."""

    ticker: str
    shares: float | None = None
    avg_cost: float | None = None  # in the listing currency
    account: str = "-"
    bucket: str = "other"
    name: str = ""
    # Mutual funds have no yfinance quote, so their value/cost is carried
    # directly in JPY — stale as of the statement date, and flagged as such.
    manual_value_jpy: float | None = None
    manual_cost_jpy: float | None = None
    # Share of this position exposed to non-JPY currencies. A TSE-listed world
    # index (1554) is quoted in yen but is ~95% foreign underneath, so listing
    # currency alone understates FX risk. Defaults by listing currency.
    fx_exposure: float | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> Position:
        return cls(
            ticker=str(raw["ticker"]).strip(),
            shares=raw.get("shares"),
            avg_cost=raw.get("avg_cost"),
            account=raw.get("account") or "-",
            bucket=raw.get("bucket") or "other",
            name=raw.get("name") or "",
            manual_value_jpy=raw.get("manual_value_jpy"),
            manual_cost_jpy=raw.get("manual_cost_jpy"),
            fx_exposure=raw.get("fx_exposure"),
        )

    @property
    def is_manual(self) -> bool:
        return self.manual_value_jpy is not None


@dataclass(frozen=True)
class Holdings:
    """The holdings file, parsed."""

    as_of: str
    positions: list[Position]
    cash_jpy: float = 0.0
    cash_usd: float = 0.0
    nisa_growth_remaining_jpy: float | None = None
    source: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> Holdings:
        cash = data.get("cash") or {}
        return cls(
            as_of=data.get("as_of") or datetime.now().strftime("%Y-%m-%d"),
            positions=[Position.from_dict(p) for p in data.get("positions", [])],
            cash_jpy=float(cash.get("JPY") or 0),
            cash_usd=float(cash.get("USD") or 0),
            nisa_growth_remaining_jpy=data.get("nisa_growth_remaining_jpy"),
            source=data.get("source") or "",
        )


def load_holdings(path: Path = HOLDINGS_PATH) -> Holdings:
    if not path.exists():
        raise SystemExit(
            f"holdings file not found: {path}\n"
            f"copy config/holdings.json.example to {path} and fill in shares / avg_cost."
        )
    return Holdings.from_dict(json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# Valuation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Valued:
    """A position joined with its quote and valued in JPY."""

    position: Position
    value_jpy: float | None
    cost_jpy: float | None
    price: float | None = None
    currency: str = "USD"
    error: str | None = None

    @property
    def is_manual(self) -> bool:
        return self.position.is_manual

    @property
    def pnl_pct(self) -> float | None:
        if self.value_jpy is None or not self.cost_jpy:
            return None
        return (self.value_jpy / self.cost_jpy - 1) * 100

    @property
    def fx_exposed_jpy(self) -> float:
        """JPY amount of this position exposed to non-JPY currencies."""
        if self.value_jpy is None:
            return 0.0
        ratio = self.position.fx_exposure
        if ratio is None:
            ratio = 0.0 if self.currency == "JPY" else 1.0
        return self.value_jpy * ratio


def fetch_quotes(positions: list[Position]) -> dict[str, StockQuote]:
    """Fetch one quote per distinct priced ticker (manual positions are skipped)."""
    tickers = list(dict.fromkeys(p.ticker for p in positions if not p.is_manual))
    return fetch_stock_quotes(tickers) if tickers else {}


def fetch_fx(default: float = FX_FALLBACK) -> float:
    """Return USD/JPY, falling back to ``default`` when the fetch fails."""
    quote = fetch_stock_quotes([FX_SYMBOL]).get(FX_SYMBOL)
    if quote and quote.last_price:
        return quote.last_price
    logger.warning("USD/JPY fetch failed; falling back to %.2f", default)
    return default


def value_positions(
    positions: list[Position], quotes: dict[str, StockQuote], fx: float
) -> list[Valued]:
    """Convert every position into JPY. Pure — quotes are supplied by the caller."""
    valued: list[Valued] = []
    for p in positions:
        if p.is_manual:
            valued.append(
                Valued(
                    position=p,
                    value_jpy=float(p.manual_value_jpy),
                    cost_jpy=float(p.manual_cost_jpy) if p.manual_cost_jpy else None,
                    currency="JPY",
                )
            )
            continue
        quote = quotes.get(p.ticker)
        price = quote.last_price if quote else None
        currency = quote.currency if quote else "USD"
        rate = 1.0 if currency == "JPY" else fx
        valued.append(
            Valued(
                position=p,
                value_jpy=price * p.shares * rate if (price and p.shares) else None,
                cost_jpy=p.avg_cost * p.shares * rate if (p.avg_cost and p.shares) else None,
                price=price,
                currency=currency,
                error=quote.error if quote else "no quote",
            )
        )
    return valued


@dataclass(frozen=True)
class Snapshot:
    """Holdings + valuations + the totals every section needs."""

    holdings: Holdings
    valued: list[Valued]
    fx: float

    @property
    def cash_jpy(self) -> float:
        return self.holdings.cash_jpy + self.holdings.cash_usd * self.fx

    @property
    def equity_jpy(self) -> float:
        return sum(v.value_jpy for v in self.valued if v.value_jpy)

    @property
    def total_jpy(self) -> float:
        return self.equity_jpy + self.cash_jpy

    @property
    def foreign_jpy(self) -> float:
        """Look-through foreign exposure, including the USD cash balance."""
        return sum(v.fx_exposed_jpy for v in self.valued) + self.holdings.cash_usd * self.fx

    @property
    def unvalued_tickers(self) -> list[str]:
        """Tickers left out of the totals because shares or a quote are missing."""
        return [v.position.ticker for v in self.valued if v.value_jpy is None]

    def weight(self, value: float | None) -> float | None:
        """Return ``value`` as a percentage of total assets, or None if unknown."""
        if value is None or not self.total_jpy:
            return None
        return value / self.total_jpy * 100

    def by_bucket(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for v in self.valued:
            if v.value_jpy:
                out[v.position.bucket] = out.get(v.position.bucket, 0) + v.value_jpy
        return out

    def by_ticker(self) -> dict[str, float]:
        """Value per ticker, summed across accounts."""
        out: dict[str, float] = {}
        for v in self.valued:
            if v.value_jpy:
                out[v.position.ticker] = out.get(v.position.ticker, 0) + v.value_jpy
        return out

    def account_count(self, ticker: str) -> int:
        return sum(1 for v in self.valued if v.position.ticker == ticker and v.value_jpy)


def build_snapshot(holdings: Holdings, *, fx: float | None = None) -> Snapshot:
    """Fetch quotes and FX, then value the holdings."""
    rate = fetch_fx() if fx is None else fx
    return Snapshot(
        holdings=holdings,
        valued=value_positions(holdings.positions, fetch_quotes(holdings.positions), rate),
        fx=rate,
    )


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _yen(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


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


def _bucket_label(bucket: str) -> str:
    return BUCKET_LABELS.get(bucket, bucket)


def _render_header(s: Snapshot) -> list[str]:
    lines = [
        f"# ポートフォリオ・スナップショット {s.holdings.as_of}",
        "",
        f"- USD/JPY **{s.fx:,.2f}**（yfinance 直近値）",
        f"- 株式評価額 **¥{_yen(s.equity_jpy)}** ／ 現金 **¥{_yen(s.cash_jpy)}**"
        f" ／ 総資産 **¥{_yen(s.total_jpy)}**",
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
            f"| {label} | {p.account} | {_bucket_label(p.bucket)} "
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
        lines.append(f"| {_bucket_label(bucket)} | {_yen(value)} | {_pct(s.weight(value))} |")
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
            lines.append(f"- {_bucket_label(bucket)} 1テーマへの集中 **{w:.1f}%** → 同時に下げる部分の大きさ")

    if s.holdings.nisa_growth_remaining_jpy:
        lines.append(
            f"- NISA成長投資枠 残 **¥{s.holdings.nisa_growth_remaining_jpy:,.0f}**"
            "（配当のある円建て・長期保有向け）"
        )
    lines.append(f"- 現金余力 **¥{s.cash_jpy:,.0f}** → 分割エントリー何回分かの原資")
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


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render a portfolio snapshot.")
    parser.add_argument("--stdout", action="store_true", help="print instead of writing a file")
    parser.add_argument(
        "--holdings", type=Path, default=HOLDINGS_PATH, help="path to the holdings file"
    )
    args = parser.parse_args(argv)

    holdings = load_holdings(args.holdings)
    text = render_snapshot(build_snapshot(holdings))

    if args.stdout:
        print(text)
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"snapshot_{holdings.as_of}.md"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
