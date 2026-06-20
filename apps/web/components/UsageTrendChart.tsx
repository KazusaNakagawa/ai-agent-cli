"use client"
import { useId } from "react"

import {
  niceScale,
  summaryMetricValue,
  UsageDailySummary,
  UsageMetric,
} from "@/lib/usage-types"

type Props = {
  summary: UsageDailySummary[]
  metric: UsageMetric
}

const CHART_HEIGHT = 200
const Y_AXIS_WIDTH = 48
const PLOT_PADDING = 8

function formatTick(value: number): string {
  return Number(value.toFixed(4)).toLocaleString("en-US")
}

// Dependency-free SVG line chart of per-day totals, styled to match
// UsageBarChart (axis frame + nice gridlines). One point per day.
export function UsageTrendChart({ summary, metric }: Props) {
  const gradientId = useId()

  if (summary.length === 0) {
    return (
      <p data-testid="usage-trend-empty" className="text-sm text-muted-foreground">
        No daily summary available yet.
      </p>
    )
  }

  const values = summary.map((d) => summaryMetricValue(d, metric))
  const max = Math.max(...values, 1)
  const { niceMax, ticks } = niceScale(max)

  // Single-point series can't form a line; render points only.
  const n = summary.length
  const xFor = (i: number) =>
    n === 1 ? 50 : PLOT_PADDING + (i / (n - 1)) * (100 - 2 * PLOT_PADDING)
  const yFor = (v: number) => (1 - v / niceMax) * 100

  const points = values.map((v, i) => ({ x: xFor(i), y: yFor(v), v, day: summary[i].date }))
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ")

  return (
    <div
      data-testid="usage-trend-chart"
      role="group"
      aria-label="Usage daily trend chart"
      // pt-3 keeps the top y-tick label (translated up 50%) from colliding with
      // the section heading above; matches UsageBarChart.
      className="flex pt-3"
    >
      {/* Y-axis tick labels (visual only; values are in the title tooltips). */}
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

      <div
        data-testid="usage-trend-plot"
        className="relative flex-1 border-b border-l border-border"
        style={{ height: CHART_HEIGHT }}
      >
        {ticks.map((t) =>
          t === 0 ? null : (
            <div
              key={t}
              aria-hidden
              className="pointer-events-none absolute inset-x-0 border-t border-muted-foreground/60"
              style={{ bottom: `${(t / niceMax) * 100}%` }}
            />
          ),
        )}

        <svg
          className="absolute inset-0 h-full w-full overflow-visible"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgb(37 99 235)" stopOpacity="0.3" />
              <stop offset="100%" stopColor="rgb(37 99 235)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {n > 1 && (
            <path
              d={`${linePath} L ${points[n - 1].x} 100 L ${points[0].x} 100 Z`}
              fill={`url(#${gradientId})`}
              stroke="none"
            />
          )}
          {n > 1 && (
            <path
              data-testid="usage-trend-line"
              d={linePath}
              fill="none"
              stroke="rgb(37 99 235)"
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>

        {/* Point markers as positioned dots, with a native tooltip per day. */}
        {points.map((p, i) => (
          <span
            key={p.day}
            data-testid={`usage-trend-point-${i}`}
            title={`${p.day}: ${formatTick(p.v)}`}
            className="absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-blue-600"
            style={{ left: `${p.x}%`, top: `${p.y}%` }}
          />
        ))}
      </div>
    </div>
  )
}
