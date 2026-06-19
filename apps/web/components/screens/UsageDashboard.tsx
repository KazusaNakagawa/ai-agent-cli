"use client"
import { useCallback, useEffect, useState } from "react"

import { UsageBarChart } from "@/components/UsageBarChart"
import {
  UsageDatesResponse,
  UsageDayResponse,
  UsageMetric,
  USAGE_METRIC_LABELS,
  UsageRecord,
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
  const [dates, setDates] = useState<string[]>([])
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [records, setRecords] = useState<UsageRecord[]>([])
  const [metric, setMetric] = useState<UsageMetric>("cost_usd")
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

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
    return () => {
      cancelled = true
    }
  }, [])

  const loadDate = useCallback((date: string) => {
    setLoading(true)
    setError(null)
    setActiveIndex(null)
    fetch(`/api/usage?date=${encodeURIComponent(date)}`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<UsageDayResponse>
      })
      .then((data) => setRecords(data.records))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
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

  if (dates.length === 0) {
    return (
      <p data-testid="usage-no-dates" className="text-sm text-muted-foreground">
        No usage logs found.
      </p>
    )
  }

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
    </div>
  )
}
