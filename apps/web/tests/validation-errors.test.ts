import { describe, expect, it } from "vitest"

import { buildErrorMap } from "@/lib/validation-errors"

describe("buildErrorMap", () => {
  it("returns an empty map for non-array input", () => {
    expect(buildErrorMap(null).size).toBe(0)
    expect(buildErrorMap("oops").size).toBe(0)
    expect(buildErrorMap(undefined).size).toBe(0)
  })

  it("strips the leading 'body' segment from loc", () => {
    const map = buildErrorMap([
      { type: "missing", loc: ["body", "portfolio", "tickers"], msg: "Field required" },
    ])
    expect(map.get("portfolio/tickers")).toBe("Field required")
  })

  it("supports numeric indices in the path", () => {
    const map = buildErrorMap([
      {
        type: "string_too_short",
        loc: ["body", "watch_sectors", 0, "sector"],
        msg: "String should have at least 1 character",
      },
    ])
    expect(map.get("watch_sectors/0/sector")).toBe(
      "String should have at least 1 character",
    )
  })

  it("ignores malformed entries", () => {
    const map = buildErrorMap([
      { type: "x", loc: "not-an-array", msg: "skipped" },
      { type: "x", loc: ["body", "ok"], msg: 42 },
      { type: "x", loc: ["body", "ok"], msg: "kept" },
    ])
    expect(map.size).toBe(1)
    expect(map.get("ok")).toBe("kept")
  })
})
