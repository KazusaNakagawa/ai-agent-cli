"use client"
import { useRef } from "react"

import { metricValue, UsageMetric, UsageRecord } from "@/lib/usage-types"
import { cn } from "@/lib/utils"

type Props = {
  records: UsageRecord[]
  metric: UsageMetric
  /** Index of the focused/hovered bar, or null. Controlled by the parent. */
  activeIndex?: number | null
  onActiveChange?: (index: number | null) => void
}

const CHART_HEIGHT = 240

// Pure presentational SVG bar chart. One bar per record; bar height is scaled
// to the max value of the selected metric. Hover/keyboard focus reports the
// active bar index to the parent so a detail tooltip can be rendered (#227).
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

  const focusBar = (index: number) => {
    const clamped = Math.max(0, Math.min(records.length - 1, index))
    barRefs.current[clamped]?.focus()
  }

  return (
    <div
      data-testid="usage-bar-chart"
      role="group"
      aria-label="Usage bar chart"
      className="flex items-end gap-1"
      style={{ height: CHART_HEIGHT }}
      onMouseLeave={() => onActiveChange?.(null)}
    >
      {records.map((record, i) => {
        const value = values[i]
        const heightPct = (value / max) * 100
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
            onBlur={() => onActiveChange?.(null)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") {
                e.preventDefault()
                focusBar(i + 1)
              } else if (e.key === "ArrowLeft") {
                e.preventDefault()
                focusBar(i - 1)
              }
            }}
          >
            <span
              data-testid={`usage-bar-fill-${i}`}
              className={cn(
                "w-full rounded-t transition-colors",
                active ? "bg-primary" : "bg-primary/60 hover:bg-primary/80",
              )}
              style={{ height: `${heightPct}%` }}
            />
          </button>
        )
      })}
    </div>
  )
}
