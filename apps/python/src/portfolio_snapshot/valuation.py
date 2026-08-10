"""Quote fetching and JPY valuation.

The only part of the package that touches the network; ``value_positions`` is
pure so the rest can be tested without it.
"""
from __future__ import annotations

from src.fetcher.stocks import StockQuote, fetch_stock_quotes
from src.logger import get_logger

from .models import Holdings, Position, Snapshot, Valued

logger = get_logger(__name__)

FX_SYMBOL = "JPY=X"
FX_FALLBACK = 157.0


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
        # `is not None`, not truthiness: a price or a holding of exactly 0 is a
        # known value, while a missing one has to stay unvalued.
        priced = price is not None and p.shares is not None
        valued.append(
            Valued(
                position=p,
                value_jpy=price * p.shares * rate if priced else None,
                cost_jpy=(
                    p.avg_cost * p.shares * rate
                    if (p.avg_cost is not None and p.shares is not None)
                    else None
                ),
                price=price,
                currency=currency,
                error=quote.error if quote else "no quote",
            )
        )
    return valued


def build_snapshot(holdings: Holdings, *, fx: float | None = None) -> Snapshot:
    """Fetch quotes (and FX unless supplied), then value the holdings."""
    rate = fetch_fx() if fx is None else fx
    return Snapshot(
        holdings=holdings,
        valued=value_positions(holdings.positions, fetch_quotes(holdings.positions), rate),
        fx=rate,
        fx_is_override=fx is not None,
    )
