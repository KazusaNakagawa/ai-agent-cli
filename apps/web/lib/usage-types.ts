import { formatLocalDate } from "@/lib/utils"

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
// 7-day window includes today plus the previous six days; rows dated after
// `today` are excluded so the window stays bounded on both ends.
export function filterSummaryByRange(
  summary: UsageDailySummary[],
  range: UsageRange,
  today: string,
): UsageDailySummary[] {
  const days = USAGE_RANGE_DAYS[range]
  if (days === null) return summary
  const base = new Date(`${today}T00:00:00`)
  base.setDate(base.getDate() - (days - 1))
  const cutoff = formatLocalDate(base)
  return summary.filter((d) => d.date >= cutoff && d.date <= today)
}

export type UsageRangeTotals = {
  /** Number of days with at least one recorded call. */
  days: number
  calls: number
  cost_usd: number
  /** Input + output + cache read + cache creation, summed across the range. */
  tokens: number
}

// Totals for the visible range, shown above the charts so the screen answers
// "how much did this period cost", not only "what did each run cost" (#428).
export function summarizeRange(summary: UsageDailySummary[]): UsageRangeTotals {
  return summary.reduce<UsageRangeTotals>(
    (acc, day) => ({
      days: acc.days + 1,
      calls: acc.calls + day.calls,
      cost_usd: acc.cost_usd + day.cost_usd,
      tokens:
        acc.tokens +
        day.input_tokens +
        day.output_tokens +
        day.cache_read_tokens +
        day.cache_creation_tokens,
    }),
    { days: 0, calls: 0, cost_usd: 0, tokens: 0 },
  )
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
// are excluded — different units can't share a stack. Each segment is a vertical
// gradient between adjacent blue shades so the whole stack reads as one smooth
// dark→light gradient (matching the single-metric bar) while staying distinct.
export type TokenSegment = {
  key: "input_tokens" | "output_tokens" | "cache_read_tokens" | "cache_creation_tokens"
  label: string
  /** Gradient class for the stacked bar segment. */
  className: string
  /** Solid representative color for the legend swatch. */
  swatchClassName: string
}

export const TOKEN_SEGMENTS: TokenSegment[] = [
  { key: "input_tokens", label: "Input", className: "bg-gradient-to-t from-blue-700 to-blue-600", swatchClassName: "bg-blue-700" },
  { key: "output_tokens", label: "Output", className: "bg-gradient-to-t from-blue-600 to-blue-500", swatchClassName: "bg-blue-600" },
  { key: "cache_read_tokens", label: "Cache read", className: "bg-gradient-to-t from-blue-500 to-blue-400", swatchClassName: "bg-blue-500" },
  { key: "cache_creation_tokens", label: "Cache creation", className: "bg-gradient-to-t from-blue-400 to-blue-300", swatchClassName: "bg-blue-400" },
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
// Axis ticks and range totals read as plain money ("$1.30", "$23.95")...
const _axisCurrencyFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
// ...except below a dime, where two decimals would flatten a cheap run to
// "$0.01" or "$0.00" — there we keep up to four.
const _smallCurrencyFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})
const _SMALL_COST_THRESHOLD = 0.1
const _numberFmt = new Intl.NumberFormat("en-US")

// Render a chart value in the unit its metric implies: cost carries a "$",
// duration reads in seconds, token counts are plain grouped integers. Used by
// both charts' axis ticks and the range totals so units never disagree.
export function formatMetricValue(metric: UsageChartMetric, value: number): string {
  if (metric === "cost_usd") {
    const fmt =
      Math.abs(value) < _SMALL_COST_THRESHOLD ? _smallCurrencyFmt : _axisCurrencyFmt
    return fmt.format(value)
  }
  if (metric === "duration_ms") return `${(value / 1000).toFixed(1)}s`
  return _numberFmt.format(Number(value.toFixed(4)))
}

// Pick which x-axis positions get a visible label. Dense series (a year of
// "All time" points) would otherwise overlap into mush, so thin them to at most
// `max` labels at an even stride, always keeping the first and last.
export function axisLabelIndices(count: number, max: number): number[] {
  if (count <= 0) return []
  if (count <= max) return Array.from({ length: count }, (_, i) => i)
  const stride = Math.ceil((count - 1) / (max - 1))
  const picked: number[] = []
  for (let i = 0; i < count - 1; i += stride) picked.push(i)
  picked.push(count - 1)
  return picked
}

const _ISO_TIME_RE = /T(\d{2}):(\d{2})/

// "2026-06-20T05:06:30" -> "05:06". The date is already fixed by the Date select,
// so the bar-chart x-axis only needs the time of day.
export function formatShortTime(timestamp: string): string {
  const m = _ISO_TIME_RE.exec(timestamp)
  return m ? `${m[1]}:${m[2]}` : timestamp
}

const _ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/

// "2026-06-24" -> "06/24". Year is dropped because the axis is always within one
// range; non-ISO input is returned untouched rather than mangled.
export function formatShortDate(iso: string): string {
  const m = _ISO_DATE_RE.exec(iso)
  return m ? `${m[2]}/${m[3]}` : iso
}

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
