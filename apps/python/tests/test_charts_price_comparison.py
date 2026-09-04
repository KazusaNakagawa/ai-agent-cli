from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from src.charts import price_comparison as pc_module
from src.charts.price_comparison import (
    generate_price_comparison,
    normalize_to_index,
    render_price_comparison,
)


def _close_df() -> pd.DataFrame:
    # index = dates, columns = tickers
    idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
    return pd.DataFrame(
        {"PLTR": [10.0, 11.0, 12.0], "NVDA": [100.0, 90.0, 110.0]},
        index=idx,
    )


def test_normalize_rebases_each_column_to_100():
    out = normalize_to_index(_close_df())
    # First row is exactly 100 for every column.
    assert out.iloc[0]["PLTR"] == pytest.approx(100.0)
    assert out.iloc[0]["NVDA"] == pytest.approx(100.0)
    # Later rows are value / first * 100.
    assert out.iloc[1]["PLTR"] == pytest.approx(110.0)  # 11/10*100
    assert out.iloc[2]["NVDA"] == pytest.approx(110.0)  # 110/100*100


def test_normalize_drops_columns_with_unusable_first_value():
    idx = pd.to_datetime(["2026-01-01", "2026-01-02"])
    df = pd.DataFrame(
        {"OK": [5.0, 6.0], "ZERO": [0.0, 1.0], "NAN": [float("nan"), 2.0]},
        index=idx,
    )
    out = normalize_to_index(df)
    assert list(out.columns) == ["OK"]


def test_render_writes_a_nonempty_png(tmp_path: Path):
    out_path = tmp_path / "chart.png"
    result = render_price_comparison(_close_df(), out_path)
    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0


@pytest.fixture(autouse=True)
def _clear_font_cache():
    """_cjk_font_name is lru_cached; a test that patches the candidate list
    would otherwise be decided by whichever test ran first.

    getattr: tests that monkeypatch _cjk_font_name itself replace it with a
    plain function, which carries no cache to clear.
    """
    def _clear():
        clear = getattr(pc_module._cjk_font_name, "cache_clear", None)
        if clear is not None:
            clear()

    _clear()
    yield
    _clear()


class _CapturingAxes:
    """Records the axes calls the assertions below care about."""

    def __init__(self, real):
        self._real = real
        self.yscale = None
        self.title = None
        self.annotations = []

    def __getattr__(self, name):
        return getattr(self._real, name)

    def set_yscale(self, scale, *a, **k):
        self.yscale = scale
        return self._real.set_yscale(scale, *a, **k)

    def set_title(self, label, *a, **k):
        self.title = label
        return self._real.set_title(label, *a, **k)

    def annotate(self, text, *a, **k):
        self.annotations.append(text)
        return self._real.annotate(text, *a, **k)


def _render_capturing(tmp_path, monkeypatch) -> _CapturingAxes:
    """Render once, returning the recorder wrapped around the real axes."""
    real_subplots = pc_module.plt.subplots
    captured = {}

    def _subplots(*a, **k):
        fig, ax = real_subplots(*a, **k)
        captured["ax"] = _CapturingAxes(ax)
        return fig, captured["ax"]

    monkeypatch.setattr(pc_module.plt, "subplots", _subplots)
    render_price_comparison(_close_df(), tmp_path / "chart.png")
    return captured["ax"]


def test_render_uses_a_log_y_axis(tmp_path, monkeypatch):
    """A portfolio's indexed returns span an order of magnitude; on a linear
    axis every line but the leader collapses onto the baseline."""
    assert _render_capturing(tmp_path, monkeypatch).yscale == "log"


def test_render_labels_each_line_end_with_its_last_value(tmp_path, monkeypatch):
    # 凡例ではなく線の終端にラベルを置く（色と銘柄の照合を読者にさせない）
    texts = _render_capturing(tmp_path, monkeypatch).annotations
    assert any("PLTR" in t and "120" in t for t in texts)  # 12/10*100
    assert any("NVDA" in t and "110" in t for t in texts)  # 110/100*100


def test_title_is_japanese_when_a_cjk_font_is_available(tmp_path, monkeypatch):
    monkeypatch.setattr(pc_module, "_cjk_font_name", lambda: "Hiragino Sans GB")
    assert "リターン比較" in _render_capturing(tmp_path, monkeypatch).title


def test_title_falls_back_to_english_without_a_cjk_font(tmp_path, monkeypatch):
    """Linux CI ships no CJK face — a Japanese title there would render as a
    row of tofu boxes, so the label language follows the font."""
    monkeypatch.setattr(pc_module, "_cjk_font_name", lambda: None)
    title = _render_capturing(tmp_path, monkeypatch).title
    assert "Return comparison" in title
    assert title.isascii()


def test_cjk_font_name_is_none_when_no_candidate_exists(monkeypatch):
    monkeypatch.setattr(pc_module, "_CJK_FONT_CANDIDATES", ("/nonexistent/font.ttc",))
    assert pc_module._cjk_font_name() is None


def test_render_drops_non_positive_values(tmp_path):
    """A log axis cannot place a zero; it must be dropped rather than left for
    matplotlib to clip silently."""
    idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
    df = pd.DataFrame({"A": [10.0, 0.0, 12.0]}, index=idx)
    out = render_price_comparison(df, tmp_path / "chart.png")
    assert out.stat().st_size > 0


def _yf_multiindex(tickers, with_data=True):
    """Mimic yfinance.download() output: columns are a MultiIndex
    (field, ticker) including a top-level 'Close'."""
    idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
    cols = pd.MultiIndex.from_product([["Close", "Open"], tickers])
    if with_data:
        data = {
            ("Close", tickers[0]): [10.0, 11.0, 12.0],
            ("Close", tickers[1]): [100.0, 90.0, 110.0],
            ("Open", tickers[0]): [9.0, 10.0, 11.0],
            ("Open", tickers[1]): [99.0, 89.0, 109.0],
        }
    else:
        nan = [float("nan")] * 3
        data = {(f, t): nan for f in ["Close", "Open"] for t in tickers}
    return pd.DataFrame(data, index=idx, columns=cols)


class _FixedDateTime:
    """Stub for pc_module.datetime so the filename date is deterministic
    (avoids midnight-boundary flakiness between the call and the assertion)."""

    @classmethod
    def now(cls):
        return datetime(2026, 6, 29)


def test_generate_writes_dated_png(tmp_path, monkeypatch):
    tickers = ["PLTR", "NVDA"]
    monkeypatch.setattr(pc_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(
        pc_module.yf, "download",
        lambda *a, **k: _yf_multiindex(tickers),
    )
    out = generate_price_comparison(tickers, tmp_path)
    expected = tmp_path / "price-comparison-20260629.png"
    assert out == expected
    assert out.exists() and out.stat().st_size > 0


def _yf_single_ticker_flat(ticker: str) -> pd.DataFrame:
    """Mimic yfinance.download() for a single ticker: flat DataFrame with plain
    column names (e.g. 'Close', 'Open') — NOT a MultiIndex."""
    idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
    return pd.DataFrame(
        {"Close": [10.0, 11.0, 12.0], "Open": [9.0, 10.0, 11.0]},
        index=idx,
    )


def test_generate_single_ticker_writes_dated_png(tmp_path, monkeypatch):
    """Single-ticker download returns a flat frame; _extract_close must name
    the column after the ticker so the present-filter keeps it."""
    ticker = "PLTR"
    monkeypatch.setattr(pc_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(
        pc_module.yf, "download",
        lambda *a, **k: _yf_single_ticker_flat(ticker),
    )
    out = generate_price_comparison([ticker], tmp_path)
    expected = tmp_path / "price-comparison-20260629.png"
    assert out == expected
    assert out.exists() and out.stat().st_size > 0


def test_generate_raises_when_no_usable_data(tmp_path, monkeypatch):
    tickers = ["PLTR", "NVDA"]
    monkeypatch.setattr(
        pc_module.yf, "download",
        lambda *a, **k: _yf_multiindex(tickers, with_data=False),
    )
    with pytest.raises(ValueError):
        generate_price_comparison(tickers, tmp_path)


def test_generate_raises_valueerror_when_close_column_absent(tmp_path, monkeypatch):
    """An empty / invalid-ticker download lacking a 'Close' column must surface
    as the documented ValueError, not a raw KeyError."""
    tickers = ["PLTR", "NVDA"]
    idx = pd.to_datetime(["2026-01-01", "2026-01-02"])
    no_close = pd.DataFrame({"Open": [1.0, 2.0]}, index=idx)
    monkeypatch.setattr(pc_module.yf, "download", lambda *a, **k: no_close)
    with pytest.raises(ValueError):
        generate_price_comparison(tickers, tmp_path)
