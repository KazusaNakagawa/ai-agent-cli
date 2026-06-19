"use client"
import { useRef } from "react"

import { metricValue, niceScale, UsageMetric, UsageRecord } from "@/lib/usage-types"
import { cn } from "@/lib/utils"

type Props = {
  records: UsageRecord[]
  metric: UsageMetric
  /** Index of the focused/hovered bar, or null. Controlled by the parent. */
  activeIndex?: number | null
  onActiveChange?: (index: number | null) => void
}

const CHART_HEIGHT = 240
const Y_AXIS_WIDTH = 48

// Trim trailing zeros so tick labels read "0.5" / "1000" rather than "0.50".
function formatTick(value: number): string {
  return Number(value.toFixed(4)).toLocaleString("en-US")
}

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

  const values = records.map((r) => metricValue(r, metric))
  const max = Math.max(...values, 1)
  const { niceMax, ticks } = niceScale(max)

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
    <div data-testid="usage-bar-chart" role="group" aria-label="Usage bar chart" className="flex">
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
            {formatTick(t)}
          </span>
        ))}
      </div>

      {/* Plot area: gridlines behind, bars in front. Left + bottom = axis frame. */}
      <div
        data-testid="usage-plot-area"
        className="relative flex-1 border-b border-l border-border"
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
                aria-label={`${record.label}: ${value}`}
                title={record.label}
                className="flex h-full flex-1 flex-col justify-end"
                onMouseEnter={() => onActiveChange?.(i)}
                onFocus={() => onActiveChange?.(i)}
                onBlur={handleBarBlur}
                onKeyDown={(e) => handleBarKeyDown(i, e)}
              >
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
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
