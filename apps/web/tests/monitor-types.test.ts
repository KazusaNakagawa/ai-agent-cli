import { describe, expect, it } from "vitest"

import {
  buildModelColorMap,
  MODEL_COLOR_PALETTE,
  MONITOR_METRIC_LABELS,
  monitorMetricValue,
  sinceForRange,
} from "@/lib/monitor-types"

describe("buildModelColorMap", () => {
  it("assigns a distinct color per model, stable across input order", () => {
    const a = buildModelColorMap(["claude-fable-5", "claude-sonnet-5", "claude-haiku-4-5"])
    const b = buildModelColorMap(["claude-haiku-4-5", "claude-fable-5", "claude-sonnet-5"])
    expect(a).toEqual(b)
    expect(new Set(Object.values(a)).size).toBe(3)
    for (const color of Object.values(a)) {
      expect(MODEL_COLOR_PALETTE).toContain(color)
    }
  })

  it("wraps around the palette instead of failing on many models", () => {
    const models = Array.from({ length: MODEL_COLOR_PALETTE.length + 2 }, (_, i) => `m-${i}`)
    const map = buildModelColorMap(models)
    expect(Object.keys(map)).toHaveLength(models.length)
  })

  it("returns an empty map for no models", () => {
    expect(buildModelColorMap([])).toEqual({})
  })
})

describe("sinceForRange", () => {
  it("computes an inclusive N-day window ending today", () => {
    expect(sinceForRange("7d", new Date("2026-07-11T12:00:00"))).toBe("2026-07-05")
    expect(sinceForRange("30d", new Date("2026-07-11T12:00:00"))).toBe("2026-06-12")
  })

  it("returns null for the all range", () => {
    expect(sinceForRange("all", new Date("2026-07-11T12:00:00"))).toBeNull()
  })
})

describe("monitorMetricValue", () => {
  it("selects the metric field", () => {
    const bucket = { key: "claude-sonnet-5", tokens: 120, cost_usd: 0.5 }
    expect(monitorMetricValue(bucket, "tokens")).toBe(120)
    expect(monitorMetricValue(bucket, "cost_usd")).toBe(0.5)
  })
})

describe("MONITOR_METRIC_LABELS", () => {
  it("labels both metrics", () => {
    expect(MONITOR_METRIC_LABELS.cost_usd).toMatch(/cost/i)
    expect(MONITOR_METRIC_LABELS.tokens).toMatch(/token/i)
  })
})
