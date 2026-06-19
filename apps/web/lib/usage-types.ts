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

export function metricValue(record: UsageRecord, metric: UsageMetric): number {
  return record[metric] ?? 0
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
