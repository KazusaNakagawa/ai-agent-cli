import { describe, expect, it } from "vitest"

import {
  axisLabelIndices,
  filterSummaryByRange,
  formatMetricValue,
  formatShortDate,
  niceScale,
  summarizeRange,
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

  it("drops future-dated rows past today for bounded ranges", () => {
    const withFuture = [...summary, day("2026-07-01")]
    const result = filterSummaryByRange(withFuture, "7d", "2026-06-29")
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

describe("summarizeRange", () => {
  function full(date: string, cost: number, tokens: number, calls = 1): UsageDailySummary {
    return {
      date,
      calls,
      input_tokens: tokens,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_creation_tokens: 0,
      cost_usd: cost,
    }
  }

  it("totals cost, tokens, calls and day count", () => {
    const totals = summarizeRange([full("2026-06-23", 0.5, 100, 3), full("2026-06-24", 1.3, 200, 2)])
    expect(totals.days).toBe(2)
    expect(totals.calls).toBe(5)
    expect(totals.cost_usd).toBeCloseTo(1.8, 10)
    expect(totals.tokens).toBe(300)
  })

  it("sums all four token fields, not just input", () => {
    const totals = summarizeRange([
      {
        date: "2026-06-23",
        calls: 1,
        input_tokens: 1,
        output_tokens: 2,
        cache_read_tokens: 4,
        cache_creation_tokens: 8,
        cost_usd: 0,
      },
    ])
    expect(totals.tokens).toBe(15)
  })

  it("returns zeros for an empty range", () => {
    expect(summarizeRange([])).toEqual({ days: 0, calls: 0, cost_usd: 0, tokens: 0 })
  })
})

describe("formatMetricValue", () => {
  it("renders cost as currency with at least two decimals", () => {
    expect(formatMetricValue("cost_usd", 0.4)).toBe("$0.40")
    expect(formatMetricValue("cost_usd", 1.3)).toBe("$1.30")
  })

  it("keeps sub-cent precision for small costs", () => {
    expect(formatMetricValue("cost_usd", 0.0123)).toBe("$0.0123")
    expect(formatMetricValue("cost_usd", 0.05)).toBe("$0.05")
  })

  it("rounds a large total to cents instead of four decimals", () => {
    expect(formatMetricValue("cost_usd", 23.9454)).toBe("$23.95")
  })

  it("groups token counts and drops the currency sign", () => {
    expect(formatMetricValue("input_tokens", 165437)).toBe("165,437")
    expect(formatMetricValue("all", 165437)).toBe("165,437")
  })

  it("renders duration in seconds", () => {
    expect(formatMetricValue("duration_ms", 1500)).toBe("1.5s")
  })

  it("renders zero without special-casing", () => {
    expect(formatMetricValue("cost_usd", 0)).toBe("$0.00")
    expect(formatMetricValue("input_tokens", 0)).toBe("0")
  })
})

describe("axisLabelIndices", () => {
  it("labels every point when they fit", () => {
    expect(axisLabelIndices(5, 8)).toEqual([0, 1, 2, 3, 4])
  })

  it("thins dense series down to at most max labels, keeping first and last", () => {
    const picked = axisLabelIndices(30, 8)
    expect(picked.length).toBeLessThanOrEqual(8)
    expect(picked[0]).toBe(0)
    expect(picked[picked.length - 1]).toBe(29)
  })

  it("handles a single point and an empty series", () => {
    expect(axisLabelIndices(1, 8)).toEqual([0])
    expect(axisLabelIndices(0, 8)).toEqual([])
  })
})

describe("formatShortDate", () => {
  it("shortens an ISO date to MM/DD", () => {
    expect(formatShortDate("2026-06-24")).toBe("06/24")
  })

  it("passes through anything that is not an ISO date", () => {
    expect(formatShortDate("20260624")).toBe("20260624")
  })
})
