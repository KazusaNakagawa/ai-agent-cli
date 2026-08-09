"""Holdings input model and the valued snapshot built from it.

Data shapes only — fetching lives in ``valuation``, Markdown in ``render``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HOLDINGS_PATH = Path(__file__).parents[2] / "config" / "holdings.json"
EXAMPLE_PATH = HOLDINGS_PATH.with_name("holdings.json.example")
OUTPUT_DIR = Path(__file__).parents[2] / "output" / "portfolio"

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


def bucket_label(bucket: str) -> str:
    return BUCKET_LABELS.get(bucket, bucket)


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
        # Name both paths: with --holdings the missing file is not the default
        # one, and "copy the example to <that path>" is the actionable fix.
        raise SystemExit(
            f"holdings file not found: {path}\n"
            f"copy the template and fill in shares / avg_cost:\n"
            f"  cp {EXAMPLE_PATH} {path}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # Hand-edited config: a raw traceback hides which file and where.
        raise SystemExit(
            f"holdings file is not valid JSON: {path}\n"
            f"  line {exc.lineno}, column {exc.colno}: {exc.msg}\n"
            f"a trailing comma or an unquoted key is the usual cause; "
            f"compare against {EXAMPLE_PATH}"
        ) from exc
    return Holdings.from_dict(data)


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


@dataclass(frozen=True)
class Snapshot:
    """Holdings + valuations + the totals every section needs."""

    holdings: Holdings
    valued: list[Valued]
    fx: float
    # True when the rate came from --fx rather than a live quote, so the header
    # can't claim a hand-picked rate is the market's.
    fx_is_override: bool = False

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
        """Distinct accounts holding this ticker.

        Counted by account, not by row: one account can hold the same ticker on
        several lines (a split purchase), and those must not read as "held
        across accounts".
        """
        return len(
            {
                v.position.account
                for v in self.valued
                if v.position.ticker == ticker and v.value_jpy
            }
        )
