// Types and helpers for the Monitor tab (GET /api/usage/monitor).
// This is the all-traffic transcript aggregation — a separate data source
// from the Settings > Usage modal, which shows app-run costs only.

export type MonitorBucket = {
  key: string
  tokens: number
  cost_usd: number
}

export type MonitorDateEntry = {
  date: string // ISO YYYY-MM-DD
  tokens: number
  cost_usd: number
  models: MonitorBucket[]
}

export type MonitorResponse = {
  total_tokens: number
  total_cost_usd: number
  by_project: MonitorBucket[]
  by_date: MonitorDateEntry[]
  by_model: MonitorBucket[]
  unpriced_models: string[]
}

export type MonitorMetric = "cost_usd" | "tokens"

export const MONITOR_METRIC_LABELS: Record<MonitorMetric, string> = {
  cost_usd: "Cost (USD)",
  tokens: "Tokens",
}

export type MonitorRange = "7d" | "30d" | "all"

export const MONITOR_RANGE_LABELS: Record<MonitorRange, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  all: "All time",
}

const RANGE_DAYS: Record<MonitorRange, number | null> = {
  "7d": 7,
  "30d": 30,
  all: null,
}

/** Inclusive start date (YYYY-MM-DD, local time) for a range ending today. */
export function sinceForRange(range: MonitorRange, now: Date = new Date()): string | null {
  const days = RANGE_DAYS[range]
  if (days === null) return null
  const start = new Date(now)
  start.setDate(start.getDate() - (days - 1))
  const y = start.getFullYear()
  const m = String(start.getMonth() + 1).padStart(2, "0")
  const d = String(start.getDate()).padStart(2, "0")
  return `${y}-${m}-${d}`
}

export function monitorMetricValue(bucket: MonitorBucket, metric: MonitorMetric): number {
  return bucket[metric] ?? 0
}

// Series colors are theme-aware CSS custom properties defined in
// globals.css (:root for light, .dark for dark) — muted hues stepped per
// surface and validated for CVD separation. Assignment is by sorted model
// id so the same model keeps the same color across every chart and across
// renders regardless of response order.
export const MODEL_COLOR_PALETTE = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
  "var(--series-8)",
] as const

export function buildModelColorMap(models: string[]): Record<string, string> {
  const map: Record<string, string> = {}
  const sorted = Array.from(new Set(models)).sort()
  sorted.forEach((model, i) => {
    map[model] = MODEL_COLOR_PALETTE[i % MODEL_COLOR_PALETTE.length]
  })
  return map
}
