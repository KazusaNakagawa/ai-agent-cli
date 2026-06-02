import { describe, expect, it } from "vitest"

import { formatLocalDate } from "@/lib/utils"

describe("formatLocalDate", () => {
  it("formats a Date via local-time getters (not UTC)", () => {
    // new Date(y, m, d, h, ...) constructs in local time, and the matching
    // getFullYear / getMonth / getDate readers return those same local
    // components — so this round-trip is TZ-independent.
    const d = new Date(2026, 5, 3, 7, 47, 0) // local Jun 3 2026 07:47
    expect(formatLocalDate(d)).toBe("2026-06-03")
  })

  it("zero-pads single-digit months and days", () => {
    expect(formatLocalDate(new Date(2026, 0, 5))).toBe("2026-01-05")
  })
})
