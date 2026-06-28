# Usage 期間レンジプルダウン 設計書

- 日付: 2026-06-29
- 対象 Issue: Usage の一週間分を表示する項目を pulldown で追加。一週間の間に日毎でどれだけトークン消費したかなど分析したい。

## 背景

Config > Usage ダッシュボード (`apps/web/components/screens/UsageDashboard.tsx`) は既に
以下を備えている。

- **Date プルダウン** (`/api/usage/dates`) — 単日を選び、その日の run 単位の棒グラフ
  (`UsageBarChart`) を表示
- **Metric プルダウン** — cost / input / output / cache / duration / all を切替
- **Daily trend チャート** (`/api/usage/summary` → `UsageTrendChart`) — 日別合算を
  **全期間** ISO 日付昇順で折れ線表示

日毎のトークン消費トレンド自体は既に可視化されているが、常に全期間表示のため
「直近1週間の消費を分析する」には不便。本対応では **表示範囲を絞り込む期間レンジ
プルダウン** を追加する。

## ゴール / 非ゴール

### ゴール
- 日別トレンドチャートの表示範囲を「Last 7 days / Last 30 days / All time」で切替える
  プルダウンを追加する。初期値は **Last 7 days**。
- 絞り込みは **暦日ベース**（今日から N-1 日前の日付以降を残す）で行う。

### 非ゴール
- Per run 棒グラフ・Date プルダウンの挙動は変更しない（単日詳細用として維持）。
- バックエンド (`/api/usage/*`) の変更はしない。
- 集計値（合計・日平均など）の新規サマリ表示は追加しない（YAGNI）。

## 設計方針: クライアント側フィルタ（バックエンド変更なし）

`/api/usage/summary` は既に全日分を ISO 日付昇順で返している。新規 API は不要で、
`UsageDashboard` が取得済みの `summary` をレンジで絞り込んだ `visibleSummary` を
`UsageTrendChart` に渡すだけで完結する。

### 暦日フィルタの定義

- レンジ `7d` → 「今日を含む直近 7 暦日」。すなわち `date >= today - 6 days`。
- レンジ `30d` → `date >= today - 29 days`。
- レンジ `all` → フィルタなし。

ログは毎日連続して存在するとは限らないため、件数 slice ではなく日付比較で残す。
比較は ISO 日付文字列 (`YYYY-MM-DD`) の辞書順比較で正しく行える。今日の基準は
ローカルタイムの `new Date()` から `YYYY-MM-DD` を生成する。

## 変更点

### 1. `apps/web/lib/usage-types.ts`
- 型・定数を追加:
  ```ts
  export type UsageRange = "7d" | "30d" | "all"

  export const USAGE_RANGE_LABELS: Record<UsageRange, string> = {
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    all: "All time",
  }

  // Number of calendar days to keep; null = no limit.
  export const USAGE_RANGE_DAYS: Record<UsageRange, number | null> = {
    "7d": 7,
    "30d": 30,
    all: null,
  }
  ```
- 純関数 `filterSummaryByRange(summary, range, today)` を追加してフィルタロジックを
  テスト可能にする:
  ```ts
  export function filterSummaryByRange(
    summary: UsageDailySummary[],
    range: UsageRange,
    today: string, // ISO YYYY-MM-DD (local)
  ): UsageDailySummary[]
  ```
  `USAGE_RANGE_DAYS[range]` が `null` ならそのまま返す。そうでなければ
  `today` から `days - 1` 日引いた下限 ISO を計算し `date >= cutoff` を残す。

### 2. `apps/web/components/screens/UsageDashboard.tsx`
- `range` state を追加（初期値 `"7d"`）。
- Metric プルダウンの隣に「Range」プルダウンを追加（`data-testid="usage-range-select"`、
  選択肢は `USAGE_RANGE_LABELS`）。
- `visibleSummary = filterSummaryByRange(summary, range, todayISO)` を算出し
  `UsageTrendChart` に渡す。
- トレンド見出しを `Daily trend ({USAGE_RANGE_LABELS[range]}) — {metric}` に変更。
- トレンドセクションの表示条件は `visibleSummary.length > 0 && metric !== "all"`。

### 3. テスト
- `apps/web/lib/usage-types.test.ts`（または既存テストファイル）に
  `filterSummaryByRange` の単体テストを追加:
  - `7d` で境界日 (`today-6`) は残り `today-7` は除外される
  - `all` は全件返す
  - 空配列・単一要素のエッジケース
- `UsageDashboard` のテストに Range プルダウンの存在と、`7d` 既定で範囲外の点が
  描画されないことを確認するケースを追加。

## エラーハンドリング
- `summary` 取得失敗時の挙動は現状維持（非致命、棒グラフは動作）。
- `filterSummaryByRange` は純関数で副作用なし。不正 `today` は呼び出し側で生成するため
  考慮不要。

## テスト計画
- [ ] `filterSummaryByRange` 単体テスト green
- [ ] `UsageDashboard` の Range プルダウンテスト green
- [ ] `apps/web` の lint / typecheck パス
- [ ] 手動: Usage 画面で Range 切替えにより折れ線の点数が変わることを確認
