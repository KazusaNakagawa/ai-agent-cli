from dataclasses import dataclass

import yfinance as yf
from src.logger import get_logger

logger = get_logger(__name__)

# Suffixes/shapes that identify a JPY-quoted listing when yfinance does not
# report a usable currency string (e.g. a mocked or partial fast_info).
_JPY_SUFFIXES = (".T", ".JP")

# Display symbols for the currencies actually held. Anything else falls back to
# its ISO code so an unexpected listing is labelled honestly rather than as USD.
_CURRENCY_SYMBOLS = {"USD": "$", "JPY": "¥", "EUR": "€", "GBP": "£"}


@dataclass(frozen=True)
class StockQuote:
    """One ticker's day-over-day move, or the error that prevented fetching it."""

    ticker: str
    last_price: float | None = None
    previous_close: float | None = None
    change_pct: float | None = None
    currency: str = "USD"
    error: str | None = None


def _currency_of(ticker: str, info) -> str:
    """Return the listing currency, falling back to the ticker's own shape.

    ``fast_info.currency`` is the authoritative source, but it is absent on some
    listings, so a suffix/all-digits check covers Japanese tickers (``4676.T``)
    when it is missing.
    """
    currency = getattr(info, "currency", None)
    if isinstance(currency, str) and currency:
        return currency.upper()
    if ticker.upper().endswith(_JPY_SUFFIXES) or ticker.isdigit():
        return "JPY"
    return "USD"


def fetch_stock_quotes(tickers: list[str]) -> dict[str, StockQuote]:
    """Fetch day-over-day moves via yfinance and return structured quotes.

    The structured form is what the JPY conversion needs (a percentage and a
    currency, not a pre-rendered string); the display helpers below build on it.
    """
    quotes: dict[str, StockQuote] = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).fast_info
            pct = (info.last_price / info.previous_close - 1) * 100
            quotes[t] = StockQuote(
                ticker=t,
                last_price=info.last_price,
                previous_close=info.previous_close,
                change_pct=pct,
                currency=_currency_of(t, info),
            )
        except Exception as e:
            logger.warning("stock fetch failed [%s]: %s", t, e)
            quotes[t] = StockQuote(ticker=t, error=f"Stock fetch error ({e})")
    return quotes


def _currency_symbol(currency: str) -> str:
    """Return the display symbol for a currency, falling back to its ISO code.

    Prices were previously always prefixed with ``$``, which mislabels a
    JPY-quoted listing (``4676.T``) as dollars.
    """
    return _CURRENCY_SYMBOLS.get(currency.upper(), f"{currency.upper()} ")


def _format_move(quote: StockQuote) -> str:
    """Render a quote the way the holdings table has always shown it."""
    if quote.error:
        return quote.error
    arrow = "↑" if quote.change_pct > 0 else "↓"
    symbol = _currency_symbol(quote.currency)
    return f"{arrow}{abs(quote.change_pct):.1f}%  ({symbol}{quote.last_price:.2f})"


def fetch_stock_move_map(tickers: list[str]) -> dict[str, str]:
    """Fetch day-over-day change via yfinance and return a ticker → display-string dict (#152).

    The local-LLM path's holdings table fills cells on the Python side, so it
    needs per-ticker values rather than one joined string. On fetch failure, an
    error string is stored and the decision left to the caller (the table renders
    it like a source cell, e.g. with `-`).
    """
    moves = {t: _format_move(q) for t, q in fetch_stock_quotes(tickers).items()}
    for t, move in moves.items():
        logger.debug("stock fetch: %s: %s", t, move)
    return moves


def to_jpy_change_pct(usd_change_pct: float, fx_change_pct: float) -> float:
    """Combine a USD-quoted move with the USD/JPY move into the JPY-denominated move.

    The two compound rather than add: a holding down 5.6% in USD on a day the
    yen weakened 0.8% is down ~4.8% in yen, which is the number that matches the
    brokerage screen.
    """
    return ((1 + usd_change_pct / 100) * (1 + fx_change_pct / 100) - 1) * 100


def _format_move_with_jpy(quote: StockQuote, fx_change_pct: float) -> str:
    """Render a quote with both its USD-quoted and JPY-converted move."""
    if quote.error:
        return quote.error
    if quote.currency != "USD":
        return _format_move(quote)

    jpy_pct = to_jpy_change_pct(quote.change_pct, fx_change_pct)
    usd_arrow = "↑" if quote.change_pct > 0 else "↓"
    jpy_arrow = "↑" if jpy_pct > 0 else "↓"
    symbol = _currency_symbol(quote.currency)
    return (
        f"ドル建て {usd_arrow}{abs(quote.change_pct):.1f}% / "
        f"円建て {jpy_arrow}{abs(jpy_pct):.1f}%  ({symbol}{quote.last_price:.2f})"
    )


def fetch_stock_moves(tickers: list[str], fx_change_pct: float | None = None) -> str:
    """Fetch day-over-day change via yfinance (free).

    When ``fx_change_pct`` (the USD/JPY day-over-day move) is supplied, each
    USD-quoted ticker also reports its JPY-converted move, so the briefing's
    numbers match what the holder actually experiences. Without it the output is
    unchanged, keeping the pipeline working when the FX fetch fails or no pair
    is configured.
    """
    quotes = fetch_stock_quotes(tickers)
    if fx_change_pct is None:
        return "\n".join(f"{t}: {_format_move(q)}" for t, q in quotes.items())
    return "\n".join(
        f"{t}: {_format_move_with_jpy(q, fx_change_pct)}" for t, q in quotes.items()
    )
