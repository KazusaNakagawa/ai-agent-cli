export type UsageRecord = {
  timestamp: string
  label: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  cost_usd: number | null
  duration_ms: number | null
}

export type UsageDayResponse = {
  date: string
  records: UsageRecord[]
}

export type UsageDatesResponse = {
  dates: string[]
}

export type UsageDailySummary = {
  date: string // ISO YYYY-MM-DD
  calls: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  cost_usd: number
}

export type UsageSummaryResponse = {
  summary: UsageDailySummary[]
}

// Numeric fields a user can chart on the y-axis.
export type UsageMetric =
  | "cost_usd"
  | "input_tokens"
  | "output_tokens"
  | "cache_read_tokens"
  | "cache_creation_tokens"
  | "duration_ms"

export const USAGE_METRIC_LABELS: Record<UsageMetric, string> = {
  cost_usd: "Cost (USD)",
  input_tokens: "Input tokens",
  output_tokens: "Output tokens",
  cache_read_tokens: "Cache read tokens",
  cache_creation_tokens: "Cache creation tokens",
  duration_ms: "Duration (ms)",
}

// Chart metric adds a synthetic "all" option that stacks the token segments.
export type UsageChartMetric = UsageMetric | "all"

export const USAGE_CHART_METRIC_LABELS: Record<UsageChartMetric, string> = {
  ...USAGE_METRIC_LABELS,
  all: "All tokens (stacked)",
}

// Token fields stacked when the chart metric is "all". `cost_usd` / `duration_ms`
// are excluded — different units can't share a stack. Colors are blue-family
// shades so the chart stays in the requested palette.
export type TokenSegment = {
  key: "input_tokens" | "output_tokens" | "cache_read_tokens" | "cache_creation_tokens"
  label: string
  className: string
}

export const TOKEN_SEGMENTS: TokenSegment[] = [
  { key: "input_tokens", label: "Input", className: "bg-blue-700" },
  { key: "output_tokens", label: "Output", className: "bg-blue-500" },
  { key: "cache_read_tokens", label: "Cache read", className: "bg-blue-400" },
  { key: "cache_creation_tokens", label: "Cache creation", className: "bg-blue-300" },
]

export function stackedTotal(record: UsageRecord): number {
  return TOKEN_SEGMENTS.reduce((sum, seg) => sum + (record[seg.key] ?? 0), 0)
}

export function metricValue(record: UsageRecord, metric: UsageMetric): number {
  return record[metric] ?? 0
}

// Daily summaries omit duration; treat missing metrics as 0 for the trend line.
export function summaryMetricValue(
  day: UsageDailySummary,
  metric: UsageMetric,
): number {
  const value = (day as unknown as Record<string, unknown>)[metric]
  return typeof value === "number" ? value : 0
}

export type NiceScale = {
  /** Top gridline value; bars are scaled against this, not the raw max. */
  niceMax: number
  /** Spacing between gridlines (a 1/2/5 × 10ⁿ "nice" number). */
  step: number
  /** Tick values from 0 to niceMax inclusive. */
  ticks: number[]
}

// Compute a "nice" axis scale: round the step up to the nearest 1/2/5 × 10ⁿ so
// gridlines land on readable intervals (e.g. max 5000 → step 1000; max 14 →
// step 2). `targetSteps` is the rough number of intervals to aim for.
export function niceScale(max: number, targetSteps = 7): NiceScale {
  if (!(max > 0) || !Number.isFinite(max)) {
    return { niceMax: 1, step: 1, ticks: [0, 1] }
  }
  const rawStep = max / targetSteps
  const magnitude = 10 ** Math.floor(Math.log10(rawStep))
  const normalized = rawStep / magnitude
  let niceUnit: number
  if (normalized <= 1) niceUnit = 1
  else if (normalized <= 2) niceUnit = 2
  else if (normalized <= 5) niceUnit = 5
  else niceUnit = 10
  const step = niceUnit * magnitude
  const niceMax = Math.ceil(max / step) * step
  const ticks: number[] = []
  // Use integer count + multiply to avoid float drift accumulating per add.
  const count = Math.round(niceMax / step)
  for (let i = 0; i <= count; i++) {
    ticks.push(Number((step * i).toPrecision(12)))
  }
  return { niceMax, step, ticks }
}

// Human-readable labels for the detail panel, in a fixed display order so the
// tooltip is predictable regardless of JSON key order.
export const USAGE_FIELD_LABELS: Record<keyof UsageRecord, string> = {
  timestamp: "Timestamp",
  label: "Label",
  cost_usd: "Cost (USD)",
  input_tokens: "Input tokens",
  output_tokens: "Output tokens",
  cache_read_tokens: "Cache read tokens",
  cache_creation_tokens: "Cache creation tokens",
  duration_ms: "Duration",
}

export const USAGE_FIELD_ORDER = Object.keys(
  USAGE_FIELD_LABELS,
) as (keyof UsageRecord)[]

const _currencyFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
})
const _numberFmt = new Intl.NumberFormat("en-US")

// Human-readable rendering of a record field for the detail tooltip:
// cost as currency, duration in seconds, token counts grouped with commas.
export function formatUsageField<K extends keyof UsageRecord>(
  key: K,
  value: UsageRecord[K],
): string {
  if (value === null || value === undefined) return "—"
  if (key === "cost_usd" && typeof value === "number") {
    return _currencyFmt.format(value)
  }
  if (key === "duration_ms" && typeof value === "number") {
    return `${(value / 1000).toFixed(1)}s`
  }
  if (typeof value === "number") {
    return _numberFmt.format(value)
  }
  return String(value)
}
