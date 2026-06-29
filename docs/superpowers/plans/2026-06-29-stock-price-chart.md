# 株価比較チャート生成 Implementation Plan (#14 MVP)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 複数銘柄の3ヶ月終値を始点=100 に正規化した比較チャート (PNG) を生成し `apps/python/output/charts/` に保存する関数群を提供する。

**Architecture:** 新パッケージ `apps/python/src/charts/`。yfinance 依存のオーケストレーション層 (`generate_price_comparison`) と、ネットワーク非依存の純関数/描画層 (`normalize_to_index`, `render_price_comparison`) を分離。matplotlib は Agg バックエンドで使用。

**Tech Stack:** Python / matplotlib (Agg) / pandas / yfinance / pytest。

## Global Constraints

- コード内コメント・docstring は **英語** で統一（チャット応答は日本語）。
- `apps/python/requirements.txt` は自動生成。**`requirements.in` のみ編集**し
  `uv pip compile requirements.in -o requirements.txt` で再生成する。
- すべてのコマンドは `apps/python/` から実行。テストランナーは `.venv/bin/pytest`。
- テストは **ネットワーク非依存**（yfinance は monkeypatch でスタブ）。
- matplotlib は `pyplot` を import する前に `matplotlib.use("Agg")` を呼ぶ。
- テストは既存パターンに合わせ `from src.charts.price_comparison import ...` でインポート。

---

### Task 1: 依存追加 + 純関数/描画層

**Files:**
- Modify: `apps/python/requirements.in`
- Regenerate: `apps/python/requirements.txt`
- Create: `apps/python/src/charts/__init__.py`
- Create: `apps/python/src/charts/price_comparison.py`
- Test: `apps/python/tests/test_charts_price_comparison.py`

**Interfaces:**
- Produces:
  - `normalize_to_index(close_df: pd.DataFrame) -> pd.DataFrame` — 各列を先頭行=100 に
    リベース。先頭値が NaN / 0 の列は除外。
  - `render_price_comparison(close_df: pd.DataFrame, out_path: Path) -> Path` — 正規化済み
    でない生の Close DataFrame を受け取り、内部で `normalize_to_index` を適用して
    折れ線 PNG を `out_path` に保存。親ディレクトリを作成。`out_path` を返す。

- [ ] **Step 1: Add matplotlib to requirements.in and recompile**

`apps/python/requirements.in` の `yfinance` 行の直後に `matplotlib` を追加する。
編集後の先頭付近:

```
requests
yfinance
matplotlib
python-dotenv
```

その後、依存を再コンパイルして同期する:

```bash
cd apps/python
uv pip compile requirements.in -o requirements.txt
uv pip sync requirements.txt
```

確認: `.venv/bin/python -c "import matplotlib; print(matplotlib.__version__)"` がバージョンを表示する。

- [ ] **Step 2: Write the failing tests (pure + render layer)**

`apps/python/tests/test_charts_price_comparison.py` を新規作成:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd apps/python && .venv/bin/pytest tests/test_charts_price_comparison.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.charts'` (import error collecting the file).

- [ ] **Step 4: Create the package and implement the pure/render layer**

`apps/python/src/charts/__init__.py` を空ファイルで作成。

`apps/python/src/charts/price_comparison.py`:

```python
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
    for col in normalized.columns:
        ax.plot(normalized.index, normalized[col], label=col)
    ax.set_title("Price comparison (normalized to 100)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Indexed price (start = 100)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out_path
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd apps/python && .venv/bin/pytest tests/test_charts_price_comparison.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
cd /Users/nakagawakazusa/work/ai-agent
git add apps/python/requirements.in apps/python/requirements.txt apps/python/src/charts/__init__.py apps/python/src/charts/price_comparison.py apps/python/tests/test_charts_price_comparison.py
git commit -m "feat(charts): add price normalization and chart rendering (#14)"
```

---

### Task 2: yfinance オーケストレーション層

**Files:**
- Modify: `apps/python/src/charts/price_comparison.py`
- Test: `apps/python/tests/test_charts_price_comparison.py`

**Interfaces:**
- Consumes: `render_price_comparison(close_df, out_path) -> Path` (Task 1)。
- Produces:
  - `generate_price_comparison(tickers: list[str], output_dir: Path, period: str = "3mo") -> Path`
    — yfinance で Close を取得し、`output_dir/price-comparison-YYYYMMDD.png` に保存して
    Path を返す。使用可能なデータが無ければ `ValueError` を送出。

- [ ] **Step 1: Write the failing tests (orchestration)**

`apps/python/tests/test_charts_price_comparison.py` の import に
`generate_price_comparison` を追加し、末尾に以下を追記する。yfinance の
multi-ticker 出力を模した MultiIndex 列 DataFrame をスタブで返す。

```python
from datetime import datetime

from src.charts import price_comparison as pc_module
from src.charts.price_comparison import generate_price_comparison


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


def test_generate_writes_dated_png(tmp_path, monkeypatch):
    tickers = ["PLTR", "NVDA"]
    monkeypatch.setattr(
        pc_module.yf, "download",
        lambda *a, **k: _yf_multiindex(tickers),
    )
    out = generate_price_comparison(tickers, tmp_path)
    expected = tmp_path / f"price-comparison-{datetime.now():%Y%m%d}.png"
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/python && .venv/bin/pytest tests/test_charts_price_comparison.py -k generate -v`
Expected: FAIL — `ImportError: cannot import name 'generate_price_comparison'`.

- [ ] **Step 3: Implement generate_price_comparison**

`apps/python/src/charts/price_comparison.py` の `render_price_comparison` の後に追記:

```python
def _extract_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Pull the Close frame out of a yfinance.download() result and keep
    only the requested tickers that are actually present, as columns."""
    close = raw["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame()
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
    raw = yf.download(tickers, period=period, progress=False)
    close = _extract_close(raw, tickers)
    if normalize_to_index(close).columns.empty:
        raise ValueError("no usable ticker data for chart")
    out_path = output_dir / f"price-comparison-{datetime.now():%Y%m%d}.png"
    return render_price_comparison(close, out_path)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/python && .venv/bin/pytest tests/test_charts_price_comparison.py -v`
Expected: PASS (5 tests total).

- [ ] **Step 5: Run the full Python suite (no regressions)**

Run: `cd apps/python && .venv/bin/pytest -q`
Expected: all tests pass (no collection errors from the new package/import).

- [ ] **Step 6: Commit**

```bash
cd /Users/nakagawakazusa/work/ai-agent
git add apps/python/src/charts/price_comparison.py apps/python/tests/test_charts_price_comparison.py
git commit -m "feat(charts): add yfinance-backed generate_price_comparison (#14)"
```

---

## Self-Review

- **Spec coverage:** パッケージ `src/charts/`（Task 1）/ matplotlib 追加+再コンパイル
  （Task 1 Step1）/ Agg バックエンド（Task 1 実装）/ `normalize_to_index`（Task 1）/
  `render_price_comparison`（Task 1）/ `generate_price_comparison`（Task 2）/ 始点=100
  正規化・先頭 NaN/0 除外（Task 1 テスト）/ 単一→複数銘柄の列正規化 `_extract_close`
  （Task 2）/ 日付ファイル名（Task 2）/ ValueError（Task 2 テスト）/ ネットワーク非依存
  （全テスト monkeypatch/スタブ）。全カバー。
- **Placeholder scan:** プレースホルダなし。各ステップに実コード・実コマンド記載。
- **Type consistency:** `normalize_to_index(df)->df`、`render_price_comparison(df, Path)->Path`、
  `generate_price_comparison(list, Path, str)->Path`、`_extract_close(df, list)->df` は
  Task 1/2 の定義と呼び出しで一致。`pc_module.yf.download` の monkeypatch 先は実装の
  `yf` import と一致。
