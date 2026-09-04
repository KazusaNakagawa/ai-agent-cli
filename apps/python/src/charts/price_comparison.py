"""Generate a normalized multi-ticker price comparison chart (#14, #465)."""
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless backend; must precede pyplot import

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import LogLocator, NullLocator, ScalarFormatter  # noqa: E402

from src.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# Dark palette. The chart is delivered alongside the briefing, where it is read
# on a phone in the morning, so the ground is dark rather than matplotlib white.
_GROUND = "#1b1c1f"
_INK = "#e8eaed"
_INK_MUTED = "#9aa0a6"
_GRID = "#3a3d42"

# Assigned by column order, so a given portfolio keeps the same color from one
# day's chart to the next.
_SERIES_COLORS = (
    "#8bc90d",
    "#4fc3f7",
    "#f4b400",
    "#ea6a5e",
    "#b388ff",
    "#4ec98a",
    "#ff9e64",
    "#c792ea",
)

# CJK-capable faces, most-preferred first. matplotlib ships none, so a Japanese
# title renders as tofu unless one of these is installed; _cjk_font_name() falls
# back to an English title rather than drawing boxes.
_CJK_FONT_CANDIDATES = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)


@lru_cache(maxsize=1)
def _cjk_font_name() -> str | None:
    """Register the first available CJK face and return its family name.

    Cached because registering a font parses the file, and a daily briefing run
    renders more than one chart. ``None`` means no CJK face is installed — the
    caller must then avoid emitting CJK text at all.
    """
    for path in _CJK_FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            font_manager.fontManager.addfont(path)
            return font_manager.FontProperties(fname=path).get_name()
        except Exception as exc:  # noqa: BLE001 — a broken font must not sink the chart
            logger.debug("could not register CJK font %s: %s", path, exc)
    logger.info("no CJK font found — chart labels fall back to English")
    return None


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


def _title(start: pd.Timestamp) -> tuple[str, str]:
    """Chart title and y-axis label, in Japanese when a CJK face is available.

    The briefing this chart ships with is Japanese, so Japanese is preferred;
    English is the fallback that keeps a font-less Linux box from rendering a
    row of tofu boxes.
    """
    stamp = f"{start:%Y/%m/%d}"
    if _cjk_font_name():
        return f"リターン比較 — {stamp} = 100（対数軸）", "指数（起点=100）"
    # Pure ASCII: the fallback runs precisely when font coverage is unknown, so
    # it must not reintroduce a glyph (an em dash, say) that could also be missing.
    return f"Return comparison - {stamp} = 100 (log scale)", "Index (start = 100)"


def _log_subs(low: float, high: float) -> tuple[float, ...]:
    """Per-decade tick positions matched to how many decades the data spans.

    A fixed 1-2-5 ladder is right for a five-year comparison spanning more than
    a decade, and nearly blank over a one-year window that lives between 70 and
    150 — there, only the single 100 tick falls inside the axis. Narrower spans
    therefore get a denser ladder.
    """
    if low <= 0 or high <= low:
        return (1.0, 2.0, 5.0)
    decades = math.log10(high / low)
    if decades > 1.5:
        return (1.0, 2.0, 5.0)
    if decades > 0.7:
        return (1.0, 1.5, 2.0, 3.0, 5.0, 7.0)
    return (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0)


def _spread(ax, values: list[float], min_gap_px: float = 13.0) -> list[float]:
    """Nudge end-of-line label positions apart so they stay readable.

    Two holdings that finish within a percent of each other would otherwise
    print their labels on top of one another. Only the label moves — the line
    it names still ends at its true value, and the printed number is the true
    one. Measured in display pixels because the axis is logarithmic, where a
    fixed data-space gap is a different visual distance at each end.
    """
    if len(values) < 2:
        return list(values)
    to_px = ax.transData.transform
    from_px = ax.transData.inverted().transform
    px = [(i, to_px((0, v))[1]) for i, v in enumerate(values)]
    px.sort(key=lambda pair: pair[1])

    spread = dict(px)
    for (prev_i, _), (i, y) in zip(px, px[1:]):
        floor = spread[prev_i] + min_gap_px
        if y < floor:
            spread[i] = floor
    return [from_px((0, spread[i]))[1] for i in range(len(values))]


def render_price_comparison(close_df: pd.DataFrame, out_path: Path) -> Path:
    """Normalize the raw Close DataFrame (index = dates, columns = tickers),
    render a multi-line comparison chart, and save it as PNG to out_path.
    Creates the parent directory if needed. Returns out_path.

    The y-axis is logarithmic: a portfolio's indexed returns routinely span an
    order of magnitude, and on a linear axis every line but the leader collapses
    onto the baseline. On a log axis equal slope means equal percentage change,
    which is the comparison the chart exists to make.
    """
    normalized = normalize_to_index(close_df)
    # A log axis cannot place non-positive values; drop them rather than let
    # matplotlib silently clip the series.
    normalized = normalized.mask(normalized <= 0)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cjk = _cjk_font_name()
    fig, ax = plt.subplots(figsize=(11, 6))
    try:
        fig.patch.set_facecolor(_GROUND)
        ax.set_facecolor(_GROUND)

        ends: list[tuple[str, str, Any, float]] = []
        for i, col in enumerate(normalized.columns):
            color = _SERIES_COLORS[i % len(_SERIES_COLORS)]
            series = normalized[col]
            ax.plot(series.index, series, color=color, lw=1.7, label=col)
            last = series.dropna()
            if not last.empty:
                ends.append((col, color, last.index[-1], float(last.iloc[-1])))

        ax.set_yscale("log")
        low, high = ax.get_ylim()
        ax.yaxis.set_major_locator(LogLocator(base=10, subs=_log_subs(low, high)))
        ax.yaxis.set_major_formatter(ScalarFormatter())
        # Minor ticks would draw unlabelled stubs between the gridlines.
        ax.yaxis.set_minor_locator(NullLocator())
        ax.axhline(100, color=_INK_MUTED, lw=1, ls="--", alpha=0.6)

        title, ylabel = _title(normalized.index[0])
        font = {"fontname": cjk} if cjk else {}
        ax.set_title(title, color=_INK, fontsize=13, pad=14, loc="left", **font)
        ax.set_ylabel(ylabel, color=_INK_MUTED, fontsize=10, **font)

        ax.grid(axis="y", color=_GRID, lw=0.7)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=_INK_MUTED, labelsize=9.5, length=0)

        # Label the line ends instead of drawing a legend: with each series
        # named where it finishes, the reader never matches colors to a key.
        # Drawn last, after the scale and limits are final, because the
        # de-collision below measures in display pixels.
        for (col, color, x, y), label_y in zip(ends, _spread(ax, [e[3] for e in ends])):
            ax.annotate(
                f" {col} {y:,.0f}",
                (x, label_y),
                xytext=(6, 0),
                textcoords="offset points",
                color=color,
                fontsize=10,
                fontweight="bold",
                va="center",
                annotation_clip=False,
            )

        fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor=_GROUND)
    finally:
        plt.close(fig)
    return out_path


def _extract_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Pull the Close frame out of a yfinance.download() result and keep
    only the requested tickers that are actually present, as columns."""
    try:
        close = raw["Close"]
    except KeyError:
        # Empty / invalid-ticker downloads may lack a "Close" column entirely;
        # normalize to an empty frame so the caller's ValueError contract holds.
        return pd.DataFrame(index=raw.index)
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
