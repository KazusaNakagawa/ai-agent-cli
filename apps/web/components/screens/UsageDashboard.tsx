"use client"
import { useCallback, useEffect, useRef, useState } from "react"

import { UsageBarChart } from "@/components/UsageBarChart"
import { UsageTrendChart } from "@/components/UsageTrendChart"
import {
  formatUsageField,
  UsageDailySummary,
  UsageDatesResponse,
  UsageDayResponse,
  UsageMetric,
  USAGE_FIELD_LABELS,
  USAGE_FIELD_ORDER,
  USAGE_METRIC_LABELS,
  UsageRecord,
  UsageSummaryResponse,
} from "@/lib/usage-types"

const METRICS: UsageMetric[] = [
  "cost_usd",
  "input_tokens",
  "output_tokens",
  "cache_read_tokens",
  "cache_creation_tokens",
  "duration_ms",
]

export function UsageDashboard() {
  // `null` = dates request still in flight; `[]` = loaded but no logs.
  const [dates, setDates] = useState<string[] | null>(null)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [records, setRecords] = useState<UsageRecord[]>([])
  const [metric, setMetric] = useState<UsageMetric>("cost_usd")
  const [summary, setSummary] = useState<UsageDailySummary[]>([])
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  // Tracks the date of the most recent request so a slower response for an
  // older date can't overwrite records for the date the user now has selected.
  const latestRequestedDate = useRef<string | null>(null)

  // Load available dates once; default to the newest.
  useEffect(() => {
    let cancelled = false
    fetch("/api/usage/dates", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<UsageDatesResponse>
      })
      .then((data) => {
        if (cancelled) return
        setDates(data.dates)
        setSelectedDate(data.dates[0] ?? null)
      })
      .catch((e) => !cancelled && setError(String(e)))
    // Daily summary for the trend chart; failure here is non-fatal (the
    // per-day bar chart still works), so we only log it.
    fetch("/api/usage/summary", { cache: "no-store" })
      .then((res) => (res.ok ? (res.json() as Promise<UsageSummaryResponse>) : null))
      .then((data) => {
        if (!cancelled && Array.isArray(data?.summary)) setSummary(data.summary)
      })
      .catch((e) => {
        // Non-fatal: the per-day bar chart still works without the trend.
        if (!cancelled) console.error("Failed to load usage summary:", e)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const loadDate = useCallback((date: string) => {
    setLoading(true)
    setError(null)
    setActiveIndex(null)
    latestRequestedDate.current = date
    fetch(`/api/usage?date=${encodeURIComponent(date)}`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<UsageDayResponse>
      })
      .then((data) => {
        // Drop responses superseded by a newer date selection.
        if (latestRequestedDate.current !== date) return
        setRecords(data.records)
      })
      .catch((e) => {
        if (latestRequestedDate.current !== date) return
        setError(String(e))
      })
      .finally(() => {
        if (latestRequestedDate.current === date) setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (selectedDate) loadDate(selectedDate)
  }, [selectedDate, loadDate])

  if (error) {
    return (
      <p data-testid="usage-error" className="text-sm text-destructive">
        Failed to load usage data: {error}
      </p>
    )
  }

  if (dates === null) {
    return (
      <p data-testid="usage-dates-loading" className="text-sm text-muted-foreground">
        Loading usage dates…
      </p>
    )
  }

  if (dates.length === 0) {
    return (
      <p data-testid="usage-no-dates" className="text-sm text-muted-foreground">
        No usage logs found.
      </p>
    )
  }

  const activeRecord = activeIndex !== null ? records[activeIndex] : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          Date
          <select
            data-testid="usage-date-select"
            value={selectedDate ?? ""}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          >
            {dates.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Metric
          <select
            data-testid="usage-metric-select"
            value={metric}
            onChange={(e) => setMetric(e.target.value as UsageMetric)}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          >
            {METRICS.map((m) => (
              <option key={m} value={m}>
                {USAGE_METRIC_LABELS[m]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="space-y-1">
        <h3 className="text-sm font-medium text-muted-foreground">
          Per run — {USAGE_METRIC_LABELS[metric]}
        </h3>
        {loading ? (
          <p data-testid="usage-loading" className="text-sm text-muted-foreground">
            Loading…
          </p>
        ) : (
          <UsageBarChart
            records={records}
            metric={metric}
            activeIndex={activeIndex}
            onActiveChange={setActiveIndex}
          />
        )}
      </section>

      {summary.length > 0 && (
        <section className="space-y-1">
          <h3 className="text-sm font-medium text-muted-foreground">
            Daily trend — {USAGE_METRIC_LABELS[metric]}
          </h3>
          <UsageTrendChart summary={summary} metric={metric} />
        </section>
      )}

      {activeRecord ? (
        <dl
          data-testid="usage-detail"
          role="status"
          aria-live="polite"
          className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-md border p-3 text-sm sm:grid-cols-3"
        >
          {USAGE_FIELD_ORDER.map((key) => (
            <div key={key} className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{USAGE_FIELD_LABELS[key]}</dt>
              <dd className="font-medium">
                {formatUsageField(key, activeRecord[key])}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p data-testid="usage-detail-hint" className="text-sm text-muted-foreground">
          Hover or focus a bar to see its details.
        </p>
      )}
    </div>
  )
}
