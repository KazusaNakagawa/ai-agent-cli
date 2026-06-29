# Usage 期間レンジプルダウン Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Usage ダッシュボードの日別トレンドチャートに、表示範囲を「Last 7 days / Last 30 days / All time」で切替える期間レンジプルダウンを追加する。

**Architecture:** バックエンド変更なし。`/api/usage/summary` が返す全日分の `summary` を、純関数 `filterSummaryByRange` で暦日ベースに絞り込み、`UsageTrendChart` に渡す。期間選択 state を `UsageDashboard` に持たせる。

**Tech Stack:** Next.js 14 (App Router) / React / TypeScript / Vitest + Testing Library。

## Global Constraints

- コード内コメント・docstring は **英語** で書く（チャット応答は日本語）。
- UI 表示文言は既存に合わせ **英語**（`Last 7 days` 等）。
- 既存の Date / Metric プルダウン・Per run 棒グラフの挙動は変更しない。
- テストランナーは `apps/web` で `npm run test`（vitest run）。lint は `npm run lint`。
- ファイルパスはすべて `apps/web/` 配下。

---

### Task 1: `filterSummaryByRange` 純関数とレンジ定数

**Files:**
- Modify: `apps/web/lib/usage-types.ts`
- Test: `apps/web/tests/usage-types.test.ts`

**Interfaces:**
- Consumes: 既存 `UsageDailySummary` 型（`{ date: string; ... }`、`date` は ISO `YYYY-MM-DD`）。
- Produces:
  - `type UsageRange = "7d" | "30d" | "all"`
  - `const USAGE_RANGE_LABELS: Record<UsageRange, string>`
  - `const USAGE_RANGE_DAYS: Record<UsageRange, number | null>`
  - `function filterSummaryByRange(summary: UsageDailySummary[], range: UsageRange, today: string): UsageDailySummary[]`

- [ ] **Step 1: Write the failing tests**

`apps/web/tests/usage-types.test.ts` の import 行に `filterSummaryByRange`, `USAGE_RANGE_DAYS`, `type UsageRange` を追加し、末尾に以下の describe を追加する。

```ts
import {
  filterSummaryByRange,
  niceScale,
  UsageDailySummary,
} from "@/lib/usage-types"

function day(date: string): UsageDailySummary {
  return {
    date,
    calls: 1,
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_creation_tokens: 0,
    cost_usd: 0,
  }
}

describe("filterSummaryByRange", () => {
  // today = 2026-06-29; 7d window keeps 2026-06-23..2026-06-29 inclusive.
  const summary = [
    day("2026-06-22"), // out (8 days back)
    day("2026-06-23"), // boundary in (6 days back)
    day("2026-06-29"), // today, in
  ]

  it("keeps the boundary day and drops the day before it for 7d", () => {
    const result = filterSummaryByRange(summary, "7d", "2026-06-29")
    expect(result.map((d) => d.date)).toEqual(["2026-06-23", "2026-06-29"])
  })

  it("returns all rows for the 'all' range", () => {
    const result = filterSummaryByRange(summary, "all", "2026-06-29")
    expect(result).toHaveLength(3)
  })

  it("keeps a 30-day window", () => {
    const result = filterSummaryByRange(summary, "30d", "2026-06-29")
    // 2026-06-22 is 7 days back, well within 30 days.
    expect(result).toHaveLength(3)
  })

  it("handles an empty summary", () => {
    expect(filterSummaryByRange([], "7d", "2026-06-29")).toEqual([])
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/web && npm run test -- usage-types`
Expected: FAIL — `filterSummaryByRange is not a function` / export なし。

- [ ] **Step 3: Implement the function and constants**

`apps/web/lib/usage-types.ts` の `UsageSummaryResponse` 型定義の直後（35 行目付近）に追記する。

```ts
// Time-range options for filtering the daily trend chart.
export type UsageRange = "7d" | "30d" | "all"

export const USAGE_RANGE_LABELS: Record<UsageRange, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  all: "All time",
}

// Number of calendar days to keep (inclusive of today); null = no limit.
export const USAGE_RANGE_DAYS: Record<UsageRange, number | null> = {
  "7d": 7,
  "30d": 30,
  all: null,
}

// Keep only summary rows within `range` calendar days of `today` (ISO
// YYYY-MM-DD). Comparison is lexicographic on ISO date strings, which is
// correct for fixed-width YYYY-MM-DD. The cutoff is `today - (days - 1)` so a
// 7-day window includes today plus the previous six days.
export function filterSummaryByRange(
  summary: UsageDailySummary[],
  range: UsageRange,
  today: string,
): UsageDailySummary[] {
  const days = USAGE_RANGE_DAYS[range]
  if (days === null) return summary
  const base = new Date(`${today}T00:00:00`)
  base.setDate(base.getDate() - (days - 1))
  // Reuse the shared local-ISO formatter so cutoff/today use one source of truth.
  const cutoff = formatLocalDate(base)
  return summary.filter((d) => d.date >= cutoff && d.date <= today)
}
```

> 実装メモ: `formatLocalDate` は `@/lib/utils` から import する（手書きの YYYY-MM-DD
> 組み立てを避け一元化）。フィルタは下限 `cutoff` に加え上限 `today` も課し、未来日の
> 行が窓に残らないようにする。

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/web && npm run test -- usage-types`
Expected: PASS（既存 `niceScale` テスト含め green）。

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/usage-types.ts apps/web/tests/usage-types.test.ts
git commit -m "feat(web): add filterSummaryByRange and usage range constants"
```

---

### Task 2: Range プルダウンを UsageDashboard に統合

**Files:**
- Modify: `apps/web/components/screens/UsageDashboard.tsx`
- Test: `apps/web/tests/usage-dashboard.test.tsx`

**Interfaces:**
- Consumes: Task 1 の `UsageRange`, `USAGE_RANGE_LABELS`, `filterSummaryByRange`、既存 `formatLocalDate`（`@/lib/utils`）。
- Produces: `data-testid="usage-range-select"` の `<select>`（UI 契約）。

- [ ] **Step 1: Write the failing test**

`apps/web/tests/usage-dashboard.test.tsx` に以下のテストを追加する。既存 `SUMMARY` は `2026-06-19` と `2026-06-20` の 2 日分。`formatLocalDate` 経由で today を決めるため、`vi.useFakeTimers` で時刻を固定する。ファイル冒頭付近の既存 describe 内に追加する（`fetchMock` のセットアップは既存ヘルパに従う。`/api/usage/dates`→DATES、`/api/usage/summary`→SUMMARY、`/api/usage?date=`→DAY を返すルーティングは既存テストのパターンを踏襲すること）。

```ts
it("defaults to a 7-day range and drops out-of-window trend points", async () => {
  // Fix 'today' far past the SUMMARY dates so the 7-day default hides them.
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 6, 15)) // 2026-07-15 local
  try {
    fetchMock.mockImplementation((url: string) => {
      if (url.startsWith("/api/usage/dates")) return Promise.resolve(jsonResponse(DATES))
      if (url.startsWith("/api/usage/summary")) return Promise.resolve(jsonResponse(SUMMARY))
      return Promise.resolve(jsonResponse(DAY_20620))
    })
    render(<UsageDashboard />)

    const rangeSelect = await screen.findByTestId("usage-range-select")
    expect((rangeSelect as HTMLSelectElement).value).toBe("7d")

    // 2026-06-19/20 are >7 days before 2026-07-15, so no trend points render.
    await waitFor(() => {
      expect(screen.queryByTestId("usage-trend-point-0")).toBeNull()
    })

    // Switching to All time brings the points back.
    await userEvent.selectOptions(rangeSelect, "all")
    await waitFor(() => {
      expect(screen.getByTestId("usage-trend-point-0")).toBeInTheDocument()
    })
  } finally {
    vi.useRealTimers()
  }
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/web && npm run test -- usage-dashboard`
Expected: FAIL — `usage-range-select` が見つからない。

- [ ] **Step 3: Implement the Range pulldown**

`apps/web/components/screens/UsageDashboard.tsx` を編集する。

(a) import に追記:

```ts
import { formatLocalDate } from "@/lib/utils"
```

`@/lib/usage-types` の import 群に `filterSummaryByRange`, `UsageRange`, `USAGE_RANGE_LABELS` を追加する。

(b) `metric` state の直後に range state を追加:

```ts
  const [range, setRange] = useState<UsageRange>("7d")
```

(c) `activeRecord` を算出している箇所（`const activeRecord = ...` の手前）に追加:

```ts
  const visibleSummary = filterSummaryByRange(summary, range, formatLocalDate())
```

(d) Metric の `<label>` ブロックの直後に Range プルダウンを追加:

```tsx
        <label className="flex items-center gap-2 text-sm">
          Range
          <select
            data-testid="usage-range-select"
            value={range}
            onChange={(e) => setRange(e.target.value as UsageRange)}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          >
            {(Object.keys(USAGE_RANGE_LABELS) as UsageRange[]).map((r) => (
              <option key={r} value={r}>
                {USAGE_RANGE_LABELS[r]}
              </option>
            ))}
          </select>
        </label>
```

(e) トレンドセクションを `summary` から `visibleSummary` に差し替え、見出しにレンジを反映:

```tsx
      {visibleSummary.length > 0 && metric !== "all" && (
        <section className="space-y-1">
          <h3 className="text-sm font-medium text-muted-foreground">
            Daily trend ({USAGE_RANGE_LABELS[range]}) — {USAGE_CHART_METRIC_LABELS[metric]}
          </h3>
          <UsageTrendChart summary={visibleSummary} metric={metric} />
        </section>
      )}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/web && npm run test -- usage-dashboard`
Expected: PASS（既存 UsageDashboard テストも green のまま）。

- [ ] **Step 5: Lint and full test sweep**

Run: `cd apps/web && npm run lint && npm run test`
Expected: lint クリーン、全 vitest スイート green。

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/screens/UsageDashboard.tsx apps/web/tests/usage-dashboard.test.tsx
git commit -m "feat(web): add time-range pulldown to usage daily trend chart"
```

---

## Self-Review

- **Spec coverage:** 期間レンジプルダウン追加（Task 2）/ 初期値 7d（Task 2 step1,3）/ 暦日ベースフィルタ（Task 1）/ 選択肢 7d・30d・all（Task 1 定数）/ Per run・Date 無変更（変更箇所限定）/ バックエンド無変更（該当タスクなし、意図どおり）。全カバー。
- **Placeholder scan:** プレースホルダなし。各ステップに実コード・実コマンド記載。
- **Type consistency:** `filterSummaryByRange(summary, range, today)` のシグネチャは Task 1 定義と Task 2 呼び出しで一致。`UsageRange` / `USAGE_RANGE_LABELS` 名称一致。`formatLocalDate()` は既存 `@/lib/utils` のシグネチャ（引数省略可）に一致。
