"use client"
import { useEffect, useMemo, useState } from "react"

import { MonitorStackedChart } from "@/components/MonitorStackedChart"
import {
  buildModelColorMap,
  MonitorMetric,
  MONITOR_METRIC_LABELS,
  MonitorRange,
  MONITOR_RANGE_LABELS,
  MonitorResponse,
  sinceForRange,
} from "@/lib/monitor-types"

function formatCost(value: number): string {
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatTokens(value: number): string {
  return value.toLocaleString("en-US")
}

// All-traffic token usage monitor (Claude Code transcripts). Fetches through
// the Next /api proxy, which injects the Bearer token server-side.
export function MonitorDashboard() {
  const [data, setData] = useState<MonitorResponse | null>(null)
  const [metric, setMetric] = useState<MonitorMetric>("cost_usd")
  const [range, setRange] = useState<MonitorRange>("7d")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    const since = sinceForRange(range)
    const query = since ? `?since=${encodeURIComponent(since)}` : ""
    fetch(`/api/usage/monitor${query}`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<MonitorResponse>
      })
      .then((body) => !cancelled && setData(body))
      .catch((e) => !cancelled && setError(String(e)))
    return () => {
      cancelled = true
    }
  }, [range])

  const colorMap = useMemo(
    () => buildModelColorMap(data?.by_model.map((m) => m.key) ?? []),
    [data],
  )

  if (error) {
    return (
      <p data-testid="monitor-error" className="text-sm text-destructive">
        Failed to load monitor data: {error}
      </p>
    )
  }

  if (data === null) {
    return (
      <p data-testid="monitor-loading" className="text-sm text-muted-foreground">
        Loading usage monitor…
      </p>
    )
  }

  const formatValue = metric === "cost_usd" ? formatCost : formatTokens
  const totalValue =
    metric === "cost_usd" ? formatCost(data.total_cost_usd) : formatTokens(data.total_tokens)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          Metric
          <select
            data-testid="monitor-metric-select"
            value={metric}
            onChange={(e) => setMetric(e.target.value as MonitorMetric)}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          >
            {(Object.keys(MONITOR_METRIC_LABELS) as MonitorMetric[]).map((m) => (
              <option key={m} value={m}>
                {MONITOR_METRIC_LABELS[m]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Range
          <select
            data-testid="monitor-range-select"
            value={range}
            onChange={(e) => setRange(e.target.value as MonitorRange)}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          >
            {(Object.keys(MONITOR_RANGE_LABELS) as MonitorRange[]).map((r) => (
              <option key={r} value={r}>
                {MONITOR_RANGE_LABELS[r]}
              </option>
            ))}
          </select>
        </label>
        <span data-testid="monitor-total" className="ml-auto text-sm font-medium">
          Total: {totalValue}
        </span>
      </div>

      <p className="text-xs text-muted-foreground">
        API-equivalent estimate across all Claude Code transcripts — usage runs on a
        subscription plan, not per-token billing.
      </p>

      {data.by_date.length === 0 ? (
        <p data-testid="monitor-empty" className="text-sm text-muted-foreground">
          No transcript usage found for this range.
        </p>
      ) : (
        <>
          <section className="space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground">
              Daily usage by model ({MONITOR_RANGE_LABELS[range]}) —{" "}
              {MONITOR_METRIC_LABELS[metric]}
            </h3>
            <MonitorStackedChart byDate={data.by_date} metric={metric} colorMap={colorMap} />
            <ul data-testid="monitor-legend" className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {data.by_model.map((m) => (
                <li key={m.key} className="flex items-center gap-1.5">
                  <span
                    data-testid="monitor-legend-swatch"
                    aria-hidden
                    className="inline-block h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: colorMap[m.key] }}
                  />
                  <span>{m.key}</span>
                </li>
              ))}
            </ul>
          </section>

          <div className="grid gap-6 sm:grid-cols-2">
            <section className="space-y-1">
              <h3 className="text-sm font-medium text-muted-foreground">By model</h3>
              <ul data-testid="monitor-by-model" className="space-y-1 text-sm">
                {data.by_model.map((m) => (
                  <li key={m.key} className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 truncate">
                      <span
                        aria-hidden
                        className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                        style={{ backgroundColor: colorMap[m.key] }}
                      />
                      {m.key}
                    </span>
                    <span className="tabular-nums">
                      {formatValue(metric === "cost_usd" ? m.cost_usd : m.tokens)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="space-y-1">
              <h3 className="text-sm font-medium text-muted-foreground">By project</h3>
              <ul data-testid="monitor-by-project" className="space-y-1 text-sm">
                {data.by_project.map((p) => (
                  <li key={p.key} className="flex items-center justify-between gap-2">
                    <span className="truncate" title={p.key}>
                      {p.key}
                    </span>
                    <span className="tabular-nums">
                      {formatValue(metric === "cost_usd" ? p.cost_usd : p.tokens)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}

      {data.unpriced_models.length > 0 && (
        <p data-testid="monitor-unpriced" className="text-xs text-amber-500">
          Unpriced models (excluded from cost): {data.unpriced_models.join(", ")}
        </p>
      )}
    </div>
  )
}
