import { describe, expect, it } from "vitest"

import { niceScale } from "@/lib/usage-types"

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
