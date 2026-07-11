"use client"

import {
  MonitorDateEntry,
  MonitorMetric,
  monitorMetricValue,
} from "@/lib/monitor-types"
import { niceScale } from "@/lib/usage-types"

type Props = {
  byDate: MonitorDateEntry[]
  metric: MonitorMetric
  colorMap: Record<string, string>
}

const CHART_HEIGHT = 220
const Y_AXIS_WIDTH = 56

// Compact notation (1.5M, 20M) keeps large token counts inside the narrow
// y-axis gutter instead of truncating to ",000,000".
function formatTick(value: number): string {
  if (Math.abs(value) >= 10_000) {
    return new Intl.NumberFormat("en-US", {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value)
  }
  return Number(value.toFixed(4)).toLocaleString("en-US")
}

// Dependency-free stacked bar chart: one bar per day, one colored segment per
// model. Mirrors the axis/gridline styling of UsageBarChart.
export function MonitorStackedChart({ byDate, metric, colorMap }: Props) {
  if (byDate.length === 0) return null

  const dayTotals = byDate.map((d) =>
    d.models.reduce((sum, m) => sum + monitorMetricValue(m, metric), 0),
  )
  const { niceMax, ticks } = niceScale(Math.max(...dayTotals, 0))

  return (
    <div data-testid="monitor-stacked-chart" role="group" aria-label="Daily usage by model" className="flex pt-6">
      <div
        aria-hidden
        className="relative shrink-0"
        style={{ height: CHART_HEIGHT, width: Y_AXIS_WIDTH }}
      >
        {ticks.map((t) => (
          <span
            key={t}
            className="absolute right-2 -translate-y-1/2 text-[11px] tabular-nums text-muted-foreground"
            style={{ bottom: `${(t / niceMax) * 100}%` }}
          >
            {formatTick(t)}
          </span>
        ))}
      </div>

      <div className="relative flex-1 border-b border-l border-border" style={{ height: CHART_HEIGHT }}>
        {ticks.map((t) =>
          t === 0 ? null : (
            <div
              key={t}
              aria-hidden
              className="pointer-events-none absolute inset-x-0 border-t border-muted-foreground/40"
              style={{ bottom: `${(t / niceMax) * 100}%` }}
            />
          ),
        )}

        <div className="absolute inset-0 flex items-end gap-1 px-1">
          {byDate.map((day, i) => (
            <div
              key={day.date}
              data-testid="monitor-stack-bar"
              // 2px row gap separates stacked segments so adjacent hues stay
              // distinguishable under color-vision deficiency.
              className="flex min-w-0 flex-1 flex-col-reverse gap-y-0.5 overflow-hidden rounded-t"
              style={{ height: `${(dayTotals[i] / niceMax) * 100}%` }}
              title={`${day.date}: ${formatTick(dayTotals[i])}`}
            >
              {day.models.map((m) => {
                const value = monitorMetricValue(m, metric)
                const share = dayTotals[i] > 0 ? value / dayTotals[i] : 0
                return (
                  <div
                    key={m.key}
                    data-testid="monitor-stack-segment"
                    data-model={m.key}
                    style={{
                      height: `${share * 100}%`,
                      backgroundColor: colorMap[m.key],
                    }}
                    title={`${m.key} — ${day.date}: ${formatTick(value)}`}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
