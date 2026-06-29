import { describe, expect, it } from "vitest"

import {
  filterSummaryByRange,
  niceScale,
  UsageDailySummary,
} from "@/lib/usage-types"

describe("niceScale", () => {
  it("rounds a max of 14 to a step of 2", () => {
    const { niceMax, step, ticks } = niceScale(14)
    expect(step).toBe(2)
    expect(niceMax).toBe(14)
    expect(ticks).toEqual([0, 2, 4, 6, 8, 10, 12, 14])
  })

  it("uses 1,000 steps for a max of 5,000", () => {
    const { niceMax, step, ticks } = niceScale(5000)
    expect(step).toBe(1000)
    expect(niceMax).toBe(5000)
    expect(ticks).toEqual([0, 1000, 2000, 3000, 4000, 5000])
  })

  it("rounds the top tick up past a non-multiple max", () => {
    const { niceMax, step } = niceScale(13.07)
    expect(step).toBe(2)
    expect(niceMax).toBe(14) // 13.07 rounds up to the next 2-multiple
  })

  it("handles small fractional maxima without float drift", () => {
    const { ticks } = niceScale(0.827)
    expect(ticks[0]).toBe(0)
    // Every tick should be a clean multiple of the step (no 0.30000000004).
    const step = ticks[1] - ticks[0]
    ticks.forEach((t, i) => expect(t).toBeCloseTo(step * i, 10))
  })

  it("falls back to a 0..1 scale for non-positive input", () => {
    expect(niceScale(0)).toEqual({ niceMax: 1, step: 1, ticks: [0, 1] })
  })
})

function day(date: string): UsageDailySummary {
  return {
    date,
    calls: 1,
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_creation_tokens: 0,
    cost_usd: 0,
  }
}

describe("filterSummaryByRange", () => {
  // today = 2026-06-29; 7d window keeps 2026-06-23..2026-06-29 inclusive.
  const summary = [
    day("2026-06-22"), // out (8 days back)
    day("2026-06-23"), // boundary in (6 days back)
    day("2026-06-29"), // today, in
  ]

  it("keeps the boundary day and drops the day before it for 7d", () => {
    const result = filterSummaryByRange(summary, "7d", "2026-06-29")
    expect(result.map((d) => d.date)).toEqual(["2026-06-23", "2026-06-29"])
  })

  it("returns all rows for the 'all' range", () => {
    const result = filterSummaryByRange(summary, "all", "2026-06-29")
    expect(result).toHaveLength(3)
  })

  it("keeps a 30-day window", () => {
    const result = filterSummaryByRange(summary, "30d", "2026-06-29")
    // 2026-06-22 is 7 days back, well within 30 days.
    expect(result).toHaveLength(3)
  })

  it("handles an empty summary", () => {
    expect(filterSummaryByRange([], "7d", "2026-06-29")).toEqual([])
  })
})
