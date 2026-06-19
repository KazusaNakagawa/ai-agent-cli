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

// Human-readable rendering of a record field for the detail tooltip:
// cost as currency, duration in seconds, token counts grouped with commas.
export function formatUsageField(key: keyof UsageRecord, value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (key === "cost_usd" && typeof value === "number") {
    return `$${value.toFixed(4)}`
  }
  if (key === "duration_ms" && typeof value === "number") {
    return `${(value / 1000).toFixed(1)}s`
  }
  if (typeof value === "number") {
    return value.toLocaleString("en-US")
  }
  return String(value)
}
