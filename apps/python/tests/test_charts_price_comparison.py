import math
from pathlib import Path

import pandas as pd
import pytest

from src.charts.price_comparison import (
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
