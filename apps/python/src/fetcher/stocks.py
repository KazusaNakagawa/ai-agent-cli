import yfinance as yf
from src.logger import get_logger

logger = get_logger(__name__)


def fetch_stock_move_map(tickers: list[str]) -> dict[str, str]:
    """Fetch day-over-day change via yfinance and return a ticker → display-string dict (#152).

    The local-LLM path's holdings table fills cells on the Python side, so it
    needs per-ticker values rather than one joined string. On fetch failure, an
    error string is stored and the decision left to the caller (the table renders
    it like a source cell, e.g. with `-`).
    """
    moves: dict[str, str] = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).fast_info
            pct = (info.last_price / info.previous_close - 1) * 100
            arrow = "↑" if pct > 0 else "↓"
            moves[t] = f"{arrow}{abs(pct):.1f}%  (${info.last_price:.2f})"
            logger.debug("stock fetch: %s: %s", t, moves[t])
        except Exception as e:
            logger.warning("stock fetch failed [%s]: %s", t, e)
            moves[t] = f"Stock fetch error ({e})"
    return moves


def fetch_stock_moves(tickers: list[str]) -> str:
    """Fetch day-over-day change via yfinance (free)."""
    return "\n".join(
        f"{t}: {move}" for t, move in fetch_stock_move_map(tickers).items()
    )
