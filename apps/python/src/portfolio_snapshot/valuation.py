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


def _quotable_tickers(positions: list[Position]) -> list[str]:
    """Tickers to quote: the priced positions, plus every proxy in use."""
    wanted: list[str] = []
    for p in positions:
        if not p.is_manual:
            wanted.append(p.ticker)
        if p.proxy:
            wanted.append(p.proxy.ticker)
    return list(dict.fromkeys(wanted))


def fetch_quotes(positions: list[Position]) -> dict[str, StockQuote]:
    """Fetch one quote per distinct ticker needed, proxies included."""
    tickers = _quotable_tickers(positions)
    return fetch_stock_quotes(tickers) if tickers else {}


def _proxy_factor(
    position: Position, quotes: dict[str, StockQuote], fx: float
) -> float | None:
    """Growth factor to apply to a manual value, or None if it can't be computed.

    Combines the proxy's own price change with the FX change when the position
    declares ``fx_at_manual`` — a yen-denominated fund holding US assets moves
    with both.
    """
    proxy = position.proxy
    if proxy is None:
        return None
    quote = quotes.get(proxy.ticker)
    if quote is None or not quote.last_price:
        logger.warning(
            "proxy %s for %s has no price; leaving the manual value as of %s",
            proxy.ticker,
            position.ticker,
            position.manual_as_of or "the statement date",
        )
        return None
    factor = quote.last_price / proxy.price_at_manual
    if proxy.fx_at_manual:
        factor *= fx / proxy.fx_at_manual
    return factor


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
            factor = _proxy_factor(p, quotes, fx)
            base = float(p.manual_value_jpy)
            valued.append(
                Valued(
                    position=p,
                    # Cost is the price actually paid, so it never moves with
                    # the proxy — only the current value does.
                    value_jpy=base * factor if factor is not None else base,
                    cost_jpy=float(p.manual_cost_jpy) if p.manual_cost_jpy else None,
                    currency="JPY",
                    estimated=factor is not None,
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
