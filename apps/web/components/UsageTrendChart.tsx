"use client"
import { useId, useState } from "react"

import {
  axisLabelIndices,
  formatMetricValue,
  formatShortDate,
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
// Above this many points the date labels would overlap, so they get thinned.
const MAX_X_LABELS = 8

type TooltipState = { x: number; y: number; label: string } | null

// Dependency-free SVG line chart of per-day totals, styled to match
// UsageBarChart (axis frame + nice gridlines). One point per day.
export function UsageTrendChart({ summary, metric }: Props) {
  const gradientId = useId()
  const [tooltip, setTooltip] = useState<TooltipState>(null)

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

  const labelled = new Set(axisLabelIndices(n, MAX_X_LABELS))

  return (
    <div
      data-testid="usage-trend-chart"
      role="group"
      aria-label="Usage daily trend chart"
      // pt-6 keeps the top y-tick label (translated up 50%) from colliding with
      // the section heading above; matches UsageBarChart.
      className="pt-6"
    >
    <div className="flex">
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
            {formatMetricValue(metric, t)}
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

        {/* Tooltip overlay */}
        {tooltip && (
          <div
            aria-hidden
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded bg-foreground px-2 py-1 text-[11px] tabular-nums text-background shadow"
            style={{ left: `${tooltip.x}%`, top: `${tooltip.y}%`, marginTop: "-6px" }}
          >
            {tooltip.label}
          </div>
        )}

        {/* Point markers as positioned dots with custom tooltip on hover/focus. */}
        {points.map((p, i) => {
          const label = `${p.day}: ${formatMetricValue(metric, p.v)}`
          return (
            <span
              key={p.day}
              data-testid={`usage-trend-point-${i}`}
              role="img"
              aria-label={label}
              tabIndex={0}
              className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full bg-blue-600 outline-none ring-offset-0 focus-visible:ring-2 focus-visible:ring-blue-400"
              style={{ left: `${p.x}%`, top: `${p.y}%` }}
              onMouseEnter={() => setTooltip({ x: p.x, y: p.y, label })}
              onMouseLeave={() => setTooltip(null)}
              onFocus={() => setTooltip({ x: p.x, y: p.y, label })}
              onBlur={() => setTooltip(null)}
            />
          )
        })}
      </div>
    </div>

      {/* X-axis: date under each point, thinned when the series is dense. Each
          label is positioned at its point's x% so it stays aligned with the dot. */}
      <div className="flex" aria-hidden>
        <div className="shrink-0" style={{ width: Y_AXIS_WIDTH }} />
        <div className="relative h-5 flex-1">
          {points.map((p, i) =>
            labelled.has(i) ? (
              <span
                key={p.day}
                data-testid={`usage-trend-x-label-${i}`}
                className="absolute top-1 -translate-x-1/2 whitespace-nowrap text-[11px] tabular-nums text-muted-foreground"
                style={{ left: `${p.x}%` }}
              >
                {formatShortDate(p.day)}
              </span>
            ) : null,
          )}
        </div>
      </div>
    </div>
  )
}
