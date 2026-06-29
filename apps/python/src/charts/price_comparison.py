"""Generate a normalized multi-ticker price comparison chart (#14 MVP)."""
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend; must precede pyplot import

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

from src.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def normalize_to_index(close_df: pd.DataFrame) -> pd.DataFrame:
    """Rebase each column to 100 at the first row so differently-priced
    tickers share one comparable axis. Columns whose first value is NaN or
    zero cannot be rebased and are dropped."""
    out = {}
    for col in close_df.columns:
        first = close_df[col].iloc[0]
        if pd.isna(first) or first == 0:
            continue
        out[col] = close_df[col] / first * 100
    return pd.DataFrame(out, index=close_df.index)


def render_price_comparison(close_df: pd.DataFrame, out_path: Path) -> Path:
    """Normalize the raw Close DataFrame (index = dates, columns = tickers),
    render a multi-line comparison chart, and save it as PNG to out_path.
    Creates the parent directory if needed. Returns out_path."""
    normalized = normalize_to_index(close_df)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    try:
        for col in normalized.columns:
            ax.plot(normalized.index, normalized[col], label=col)
        ax.set_title("Price comparison (normalized to 100)")
        ax.set_xlabel("Date")
        ax.set_ylabel("Indexed price (start = 100)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.savefig(out_path, dpi=120, bbox_inches="tight")
    finally:
        plt.close(fig)
    return out_path


def _extract_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Pull the Close frame out of a yfinance.download() result and keep
    only the requested tickers that are actually present, as columns."""
    close = raw["Close"]
    if isinstance(close, pd.Series):
        # Single-ticker download returns a flat Series; name the column after
        # the ticker so the downstream present-filter can find it.
        close = close.to_frame(name=tickers[0])
    present = [t for t in tickers if t in close.columns]
    return close.reindex(columns=present)


def generate_price_comparison(
    tickers: list[str],
    output_dir: Path,
    period: str = "3mo",
) -> Path:
    """Fetch Close prices via yfinance, render a normalized comparison chart,
    and save it to output_dir/price-comparison-YYYYMMDD.png. Returns the saved
    path. Raises ValueError if no usable ticker data was fetched."""
    try:
        raw = yf.download(tickers, period=period, progress=False)
    except Exception as e:
        logger.warning("price fetch failed for %s: %s", tickers, e)
        raise ValueError("no usable ticker data for chart") from e
    close = _extract_close(raw, tickers)
    if normalize_to_index(close).columns.empty:
        logger.warning("no usable close data for tickers %s", tickers)
        raise ValueError("no usable ticker data for chart")
    out_path = output_dir / f"price-comparison-{datetime.now():%Y%m%d}.png"
    return render_price_comparison(close, out_path)
