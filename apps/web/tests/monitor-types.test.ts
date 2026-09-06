import { describe, expect, it } from "vitest"

import {
  buildModelColorMap,
  fillDateGaps,
  MODEL_COLOR_PALETTE,
  MonitorDateEntry,
  MONITOR_METRIC_LABELS,
  monitorMetricValue,
  sinceForRange,
} from "@/lib/monitor-types"

function entry(date: string, tokens = 10): MonitorDateEntry {
  return {
    date,
    tokens,
    cost_usd: 1,
    models: [{ key: "claude-opus-5", tokens, cost_usd: 1 }],
  }
}

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

describe("fillDateGaps", () => {
  it("inserts empty entries for days with no activity", () => {
    const filled = fillDateGaps([entry("2026-09-05"), entry("2026-09-07")])

    expect(filled.map((d) => d.date)).toEqual(["2026-09-05", "2026-09-06", "2026-09-07"])
    expect(filled[1]).toMatchObject({ tokens: 0, cost_usd: 0, models: [] })
  })

  it("crosses month boundaries", () => {
    const filled = fillDateGaps([entry("2026-08-30"), entry("2026-09-02")])

    expect(filled.map((d) => d.date)).toEqual([
      "2026-08-30",
      "2026-08-31",
      "2026-09-01",
      "2026-09-02",
    ])
  })

  it("leaves an already-contiguous series untouched", () => {
    const input = [entry("2026-09-05"), entry("2026-09-06")]
    expect(fillDateGaps(input)).toBe(input)
  })

  it("passes through series too short to have a gap", () => {
    expect(fillDateGaps([])).toEqual([])
    const single = [entry("2026-09-05")]
    expect(fillDateGaps(single)).toBe(single)
  })

  it("refuses to expand a span wider than the 400-day cap", () => {
    const input = [entry("2024-01-01"), entry("2026-09-07")]
    expect(fillDateGaps(input)).toBe(input)
  })
})

describe("MONITOR_METRIC_LABELS", () => {
  it("labels both metrics", () => {
    expect(MONITOR_METRIC_LABELS.cost_usd).toMatch(/cost/i)
    expect(MONITOR_METRIC_LABELS.tokens).toMatch(/token/i)
  })
})
