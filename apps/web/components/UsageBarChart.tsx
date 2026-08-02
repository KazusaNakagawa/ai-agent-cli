"use client"
import { useRef } from "react"

import {
  axisLabelIndices,
  formatMetricValue,
  formatShortTime,
  metricValue,
  niceScale,
  stackedTotal,
  TOKEN_SEGMENTS,
  UsageChartMetric,
  UsageRecord,
} from "@/lib/usage-types"
import { cn } from "@/lib/utils"

type Props = {
  records: UsageRecord[]
  metric: UsageChartMetric
  /** Index of the focused/hovered bar, or null. Controlled by the parent. */
  activeIndex?: number | null
  onActiveChange?: (index: number | null) => void
}

const CHART_HEIGHT = 240
const Y_AXIS_WIDTH = 48
// A day rarely holds more than a handful of runs, but a busy chat day can; above
// this many bars the time labels overlap, so they get thinned.
const MAX_X_LABELS = 12

// Pure presentational SVG-free bar chart. Bars are scaled against a "nice"
// rounded max so they align with horizontal gridlines drawn at readable
// intervals. Hover/keyboard focus reports the active bar index to the parent
// so a detail tooltip can be rendered (#227).
export function UsageBarChart({
  records,
  metric,
  activeIndex = null,
  onActiveChange,
}: Props) {
  const barRefs = useRef<(HTMLButtonElement | null)[]>([])

  if (records.length === 0) {
    return (
      <p data-testid="usage-chart-empty" className="text-sm text-muted-foreground">
        No usage records for this date.
      </p>
    )
  }

  const stacked = metric === "all"
  const values = records.map((r) =>
    stacked ? stackedTotal(r) : metricValue(r, metric),
  )
  const max = Math.max(...values, 1)
  const { niceMax, ticks } = niceScale(max)

  const labelled = new Set(axisLabelIndices(records.length, MAX_X_LABELS))

  const focusBar = (index: number) => {
    const clamped = Math.max(0, Math.min(records.length - 1, index))
    barRefs.current[clamped]?.focus()
  }

  const handleBarBlur = (e: React.FocusEvent<HTMLButtonElement>) => {
    // Keep the active state when focus moves to another bar (arrow keys), so we
    // don't flicker to null + re-announce via aria-live.
    const next = e.relatedTarget as Node | null
    if (next && e.currentTarget.parentElement?.contains(next)) return
    onActiveChange?.(null)
  }

  const handleBarKeyDown = (i: number, e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowRight") {
      e.preventDefault()
      focusBar(i + 1)
    } else if (e.key === "ArrowLeft") {
      e.preventDefault()
      focusBar(i - 1)
    }
  }

  return (
    <div
      data-testid="usage-bar-chart"
      role="group"
      aria-label="Usage bar chart"
      // pt-6 keeps the top y-tick label (translated up 50%) clear of the heading,
      // even with wide 6-digit token counts in the "All" view.
      className="flex pt-6"
    >
      {/* Y-axis tick labels, aligned to the gridlines by bottom-offset %.
          aria-hidden: each bar already announces its value, so these would be
          redundant noise for screen readers. */}
      <div
        aria-hidden
        className="relative shrink-0"
        style={{ height: CHART_HEIGHT, width: Y_AXIS_WIDTH }}
      >
        {ticks.map((t) => (
          <span
            key={t}
            data-testid={`usage-y-tick-${t}`}
            className="absolute right-2 -translate-y-1/2 text-[11px] tabular-nums text-muted-foreground"
            style={{ bottom: `${(t / niceMax) * 100}%` }}
          >
            {formatMetricValue(metric, t)}
          </span>
        ))}
      </div>

      {/* Plot column: the framed plot area plus the x-axis label row beneath it,
          so the labels share the plot's width and stay clear of the legend. */}
      <div className="flex min-w-0 flex-1 flex-col">
      {/* Plot area: gridlines behind, bars in front. Left + bottom = axis frame. */}
      <div
        data-testid="usage-plot-area"
        className="relative w-full border-b border-l border-border"
        style={{ height: CHART_HEIGHT }}
        onMouseLeave={() => onActiveChange?.(null)}
      >
        {/* Horizontal gridlines at each tick (skip 0 — that's the x-axis). */}
        {ticks.map((t) =>
          t === 0 ? null : (
            <div
              key={t}
              data-testid={`usage-gridline-${t}`}
              aria-hidden
              className="pointer-events-none absolute inset-x-0 border-t border-muted-foreground/60"
              style={{ bottom: `${(t / niceMax) * 100}%` }}
            />
          ),
        )}

        {/* Bars row sits on top of the gridlines. */}
        <div className="absolute inset-0 flex items-end gap-1">
          {records.map((record, i) => {
            const value = values[i]
            const heightPct = (value / niceMax) * 100
            const active = activeIndex === i
            return (
              <button
                key={`${record.timestamp}-${i}`}
                ref={(el) => {
                  barRefs.current[i] = el
                }}
                type="button"
                data-testid={`usage-bar-${i}`}
                data-active={active}
                aria-label={`${record.label} ${formatShortTime(record.timestamp)}: ${formatMetricValue(metric, value)}`}
                title={record.label}
                className="flex h-full flex-1 flex-col justify-end"
                onMouseEnter={() => onActiveChange?.(i)}
                onFocus={() => onActiveChange?.(i)}
                onBlur={handleBarBlur}
                onKeyDown={(e) => handleBarKeyDown(i, e)}
              >
                {stacked ? (
                  <span
                    data-testid={`usage-bar-fill-${i}`}
                    className={cn(
                      "flex w-full flex-col-reverse overflow-hidden rounded-t transition-all",
                      active ? "brightness-110" : "brightness-100",
                    )}
                    style={{ height: `${heightPct}%` }}
                  >
                    {TOKEN_SEGMENTS.map((seg) => {
                      const segValue = record[seg.key] ?? 0
                      const total = value || 1
                      return (
                        <span
                          key={seg.key}
                          data-testid={`usage-bar-segment-${i}-${seg.key}`}
                          className={cn("w-full", seg.className)}
                          style={{ height: `${(segValue / total) * 100}%` }}
                        />
                      )
                    })}
                  </span>
                ) : (
                  <span
                    data-testid={`usage-bar-fill-${i}`}
                    className={cn(
                      "w-full rounded-t bg-gradient-to-t transition-colors",
                      active
                        ? "from-blue-700 to-blue-400"
                        : "from-blue-600 to-blue-300 hover:from-blue-700 hover:to-blue-400",
                    )}
                    style={{ height: `${heightPct}%` }}
                  />
                )}
              </button>
            )
          })}
        </div>
      </div>

        {/* X-axis: run start time under each bar. Cells mirror the bars' flex
            layout (same gap, same flex-1) so labels line up; a thinned-out bar
            still gets an empty cell to preserve that alignment. */}
        <div className="flex gap-1" aria-hidden>
          {records.map((record, i) => (
            <span
              key={`${record.timestamp}-label-${i}`}
              data-testid={labelled.has(i) ? `usage-bar-x-label-${i}` : undefined}
              className="min-w-0 flex-1 truncate pt-1 text-center text-[11px] tabular-nums text-muted-foreground"
            >
              {labelled.has(i) ? formatShortTime(record.timestamp) : ""}
            </span>
          ))}
        </div>
      </div>

      {stacked && (
        <ul
          data-testid="usage-stack-legend"
          className="ml-2 flex shrink-0 flex-col justify-start gap-1 self-center text-xs text-muted-foreground"
        >
          {TOKEN_SEGMENTS.map((seg) => (
            <li key={seg.key} className="flex items-center gap-1.5">
              <span className={cn("h-2.5 w-2.5 rounded-sm", seg.swatchClassName)} aria-hidden />
              {seg.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
