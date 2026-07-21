# 株価比較チャート生成 設計書 (MVP)

- 日付: 2026-06-29
- 対象 Issue: #14 feat: add chart generation for stock and metrics visualization

## 背景

エージェント出力を視覚的に補強するため、Python の可視化ライブラリでチャートを生成
する。Issue は複数チャート（価格比較・EPS・リターン比較・相関ヒートマップ・メトリクス
トレンド）と投稿連携（Discord / Notion）を挙げているが、本 PR は Issue が MVP と明記
する **複数銘柄の価格比較チャートを生成しローカル保存するところまで** に絞る。

## ゴール / 非ゴール

### ゴール
- 対象銘柄の3ヶ月終値推移を1枚の比較チャート（PNG）として生成し
  `apps/python/output/charts/` に保存する。
- 価格スケールの異なる銘柄を同一軸で比較できるよう、始点を 100 に正規化する。
- yfinance への依存を描画層から分離し、ネットワーク不要で単体テストできる構造にする。

### 非ゴール
- Discord / Notion への投稿連携（別 PR）。
- EPS・リターン比較・相関ヒートマップ・メトリクストレンドの各チャート（別 PR）。
- 既存ブリーフィングパイプラインへの組み込み（本 PR は生成関数の提供まで）。

## アーキテクチャ

新パッケージ `apps/python/src/charts/`:

- `apps/python/src/charts/__init__.py`
- `apps/python/src/charts/price_comparison.py` — チャート生成のメイン

依存追加: `matplotlib` を `apps/python/requirements.in` に追加し
`requirements.txt` を再コンパイル（CLAUDE.md のルール: `.in` のみ編集 →
`uv pip compile`）。

matplotlib は **Agg バックエンド** を使用する（GUI 非依存・ヘッドレス / CI 安全）。
`price_comparison.py` の import 時に `matplotlib.use("Agg")` を `pyplot` import 前に
設定する。

## ユニット分割

責務を分離し、ネットワーク非依存でテストできるようにする。

```python
# src/charts/price_comparison.py

import matplotlib
matplotlib.use("Agg")  # headless backend; must precede pyplot import
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime
from src.logger import get_logger

logger = get_logger(__name__)


def normalize_to_index(close_df: pd.DataFrame) -> pd.DataFrame:
    """Rebase each column to 100 at the first row so differently-priced
    tickers share one comparable axis. Columns whose first value is NaN or
    zero are dropped (cannot be rebased)."""


def render_price_comparison(close_df: pd.DataFrame, out_path: Path) -> Path:
    """Render a normalized multi-line price comparison chart from a Close
    DataFrame (index = dates, columns = tickers) and save it as PNG to
    out_path. Creates the parent directory if needed. Returns out_path."""


def generate_price_comparison(
    tickers: list[str],
    output_dir: Path,
    period: str = "3mo",
) -> Path:
    """Fetch Close prices via yfinance, normalize, render, and save to
    output_dir/price-comparison-YYYYMMDD.png. Returns the saved path.
    Raises ValueError if no usable ticker data was fetched."""
```

### 各ユニットの責務・インターフェース・依存

- `normalize_to_index(close_df) -> df`: 純関数。始点=100 へ正規化。yfinance/IO に
  依存しない。先頭値が NaN / 0 の列は除外。
- `render_price_comparison(close_df, out_path) -> Path`: DataFrame を受け取り PNG を
  保存。matplotlib (Agg) のみに依存。yfinance に依存しない。
- `generate_price_comparison(tickers, output_dir, period="3mo") -> Path`:
  取得 → 正規化 → 描画のオーケストレーション。yfinance に依存。

呼び出し側は `tickers` を明示的に渡す（テスト容易性）。実運用では
`src.config.CONFIG` の `portfolio.tickers` を渡すことを想定するが、本 PR では関数の
提供までとし、設定読み込みは呼び出し側の責務とする。

## データフロー

1. 呼び出し側が `tickers`（例: `["PLTR", "NVDA", "CBRS"]`）と `output_dir` を渡す。
2. `yf.download(tickers, period=period, progress=False)` で取得し `Close` を抽出。
   - 単一銘柄でも複数銘柄でも `DataFrame`（columns = tickers）に正規化する。
     yfinance は単一銘柄時に列構造が変わるため、`tickers` で `reindex` して
     列名を揃える。
3. `normalize_to_index` で始点=100 に正規化。
4. `render_price_comparison` で折れ線描画 → PNG 保存。
5. 保存先 `Path` を返す。

ファイル名は `price-comparison-YYYYMMDD.png`（`datetime.now()` のローカル日付）。
保存先 `output/charts/` は `mkdir(parents=True, exist_ok=True)` で作成。`output/` は
既に `.gitignore` 済み。

## チャート仕様

- 1 本/銘柄の折れ線。凡例に ticker 名。
- Y 軸: 正規化指数（始点=100）。X 軸: 日付。
- タイトル: `Price comparison (normalized to 100)`。
- グリッド表示。`fig.savefig(out_path, dpi=120, bbox_inches="tight")` 後に
  `plt.close(fig)` で確実に解放（メモリリーク防止）。

## エラーハンドリング

- yfinance 取得失敗・空データ: `logger.warning` でログ。
- 正規化後に有効列が 0 本（全銘柄が NaN / 取得失敗）: `generate_price_comparison` が
  `ValueError("no usable ticker data for chart")` を送出し、呼び出し側に委ねる
  （既存 `fetcher/stocks.py` のエラー文字列方式とは異なり、生成不能は例外とする）。
- 一部銘柄のみ欠損: 取得できた銘柄だけで描画を続行。

## テスト

`apps/python/tests/test_charts_price_comparison.py`:

1. `normalize_to_index`: 既知の小さな DataFrame（2 銘柄 × 3 日）で、各列の先頭が
   100.0 になり、以降が `value / first * 100` になることを検証（ネットワーク不要）。
2. `normalize_to_index`: 先頭値が 0 / NaN の列が除外されることを検証。
3. `render_price_comparison`: スタブ DataFrame を渡し、`tmp_path` に PNG が生成され
   ファイルサイズ > 0 であることを確認（matplotlib Agg、ネットワーク不要）。
4. `generate_price_comparison`: `yfinance.download` を monkeypatch でスタブし、
   end-to-end でファイルが生成され Path が返ることを確認。
5. `generate_price_comparison`: スタブが空 / 全 NaN を返すとき `ValueError` が
   送出されることを確認。

すべてネットワーク非依存（yfinance はテストで monkeypatch）。

## テスト計画

- [ ] `.venv/bin/pytest tests/test_charts_price_comparison.py -v` green
- [ ] `requirements.txt` が `requirements.in` から再生成され matplotlib を含む
- [ ] 手動: 実銘柄で `generate_price_comparison` を 1 回実行し PNG を目視確認
      （動作検証フェーズ）
