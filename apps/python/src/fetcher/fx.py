"""FX rate fetching for the daily briefing.

The portfolio is predominantly USD-denominated, so a holding's day-over-day
move quoted in USD is not the move its owner actually experiences in JPY. This
module supplies the exchange-rate context the briefing needs to report both,
plus the standing risk framing (where the rate sits inside its own 1-year
range) that a raw day-over-day percentage cannot convey.

Deliberately reports a *level and its position* rather than leading with the
daily change: a day-over-day FX move is noise at the horizon these holdings are
managed on, while "near the top of the 1-year range" is the part that bears on
a decision.
"""
from dataclasses import dataclass

import yfinance as yf

from src.logger import get_logger

logger = get_logger(__name__)

# History window used for the range/moving-average context. Long enough for a
# 200-day moving average to exist on a normal trading calendar (~250 sessions).
_HISTORY_PERIOD = "1y"

# Sessions in the moving average. Skipped (left as None) when history is short.
_MA_WINDOW = 200


@dataclass(frozen=True)
class FxQuote:
    """A single currency pair's rate plus the context needed to judge its level."""

    label: str
    rate: float
    change_pct: float
    range_low: float
    range_high: float
    # 0.0 = at the 1-year low, 100.0 = at the 1-year high.
    range_position_pct: float
    ma200: float | None
    ma200_dev_pct: float | None
    band_low: float | None = None
    band_high: float | None = None


def _closes(symbol: str) -> list[float]:
    """Return the pair's daily closes over _HISTORY_PERIOD, oldest first."""
    hist = yf.Ticker(symbol).history(period=_HISTORY_PERIOD)
    if hist is None or len(hist) == 0:
        raise ValueError(f"no history returned for {symbol}")
    closes = [float(v) for v in hist["Close"].dropna().tolist()]
    if len(closes) < 2:
        raise ValueError(f"insufficient history for {symbol} ({len(closes)} closes)")
    return closes


def fetch_fx_quote(symbol: str, label: str, band_low: float | None = None,
                   band_high: float | None = None) -> FxQuote | None:
    """Fetch one pair, or return None when the fetch fails.

    Returning None rather than raising keeps a broker/network hiccup on a
    secondary pair from taking down the whole briefing — the caller drops the
    pair and the rest of the pipeline proceeds, matching the degraded-mode
    philosophy used for the sector sweep.
    """
    try:
        closes = _closes(symbol)
    except Exception as e:  # noqa: BLE001 — yfinance raises a wide range of errors
        logger.warning("fx fetch failed [%s]: %s", symbol, e)
        return None

    rate = closes[-1]
    previous = closes[-2]
    low = min(closes)
    high = max(closes)
    span = high - low
    # A perfectly flat year would divide by zero; treat it as mid-range.
    position = ((rate - low) / span * 100) if span else 50.0

    ma200: float | None = None
    ma200_dev: float | None = None
    if len(closes) >= _MA_WINDOW:
        ma200 = sum(closes[-_MA_WINDOW:]) / _MA_WINDOW
        if ma200:
            ma200_dev = (rate / ma200 - 1) * 100

    return FxQuote(
        label=label,
        rate=rate,
        change_pct=(rate / previous - 1) * 100 if previous else 0.0,
        range_low=low,
        range_high=high,
        range_position_pct=position,
        ma200=ma200,
        ma200_dev_pct=ma200_dev,
        band_low=band_low,
        band_high=band_high,
    )


def _signed(pct: float) -> str:
    return f"{pct:+.2f}%"


def format_fx_quote(quote: FxQuote) -> str:
    """Render one pair as a single prompt line."""
    parts = [
        f"{quote.label}: {quote.rate:.2f}（前日比 {_signed(quote.change_pct)}）",
        f"1年レンジ {quote.range_low:.2f}〜{quote.range_high:.2f}"
        f"（レンジ内位置 {quote.range_position_pct:.0f}%）",
    ]
    if quote.ma200 is not None and quote.ma200_dev_pct is not None:
        parts.append(f"200日線 {quote.ma200:.2f}（乖離 {_signed(quote.ma200_dev_pct)}）")
    if quote.band_low is not None and quote.band_high is not None:
        parts.append(f"参照バンド {quote.band_low:.0f}〜{quote.band_high:.0f}")
    return " / ".join(parts)


def format_fx_context(
    quotes: list[FxQuote],
    usd_asset_share: float | None = None,
    scenario_rates: list[float] | None = None,
) -> str:
    """Render the whole FX block injected into the briefing prompt.

    ``usd_asset_share`` (0-1) and ``scenario_rates`` are optional: when both are
    supplied for a USD/JPY quote, a what-if table is appended showing the
    portfolio-level impact of each rate, holding stock prices constant. Without
    them the block is just the rate lines.
    """
    if not quotes:
        return "(取得なし)"

    lines = [f"- {format_fx_quote(q)}" for q in quotes]

    if usd_asset_share and scenario_rates:
        usd_jpy = next((q for q in quotes if "USD" in q.label.upper()), None)
        if usd_jpy and usd_jpy.rate:
            lines.append("")
            lines.append(f"- ドル建て資産の比率: {usd_asset_share * 100:.0f}%")
            lines.append("- 株価不変を前提とした為替シナリオ（資産全体への影響）:")
            for target in scenario_rates:
                impact = (target / usd_jpy.rate - 1) * usd_asset_share * 100
                lines.append(f"    - {target:.0f}円: {_signed(impact)}")

    return "\n".join(lines)


def fetch_fx_context(config) -> tuple[str, float | None]:
    """Fetch every configured pair and return (prompt block, USD/JPY day change %).

    The second element feeds the JPY-converted stock moves; it is None when
    USD/JPY is not configured or its fetch failed, in which case the caller
    reports USD-only moves exactly as before.
    """
    fx_config = getattr(config, "fx", None)
    if fx_config is None or not fx_config.pairs:
        return "", None

    quotes: list[FxQuote] = []
    for pair in fx_config.pairs:
        quote = fetch_fx_quote(pair.symbol, pair.label, pair.band_low, pair.band_high)
        if quote is not None:
            quotes.append(quote)
            logger.debug("fx fetch: %s: %.2f", quote.label, quote.rate)

    if not quotes:
        return "", None

    usd_jpy = next((q for q in quotes if "USD" in q.label.upper() and "JPY" in q.label.upper()), None)
    block = format_fx_context(quotes, fx_config.usd_asset_share, fx_config.scenario_rates)
    return block, (usd_jpy.change_pct if usd_jpy else None)
