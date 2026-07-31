import { describe, expect, it } from "vitest"

import { basename } from "@/lib/utils"

describe("basename", () => {
  it("returns the last path segment (success)", () => {
    expect(basename("src/components/App.tsx")).toBe("App.tsx")
  })

  it("returns the whole string when there's no separator (boundary)", () => {
    expect(basename("readme.md")).toBe("readme.md")
  })

  // Paths reach the UI as strings built by the host's `Path`, so a Windows
  // one must still match a filename-keyed list.
  it("treats a backslash as a separator", () => {
    expect(basename("C:\\repo\\output\\briefing_2026-08-01.md")).toBe(
      "briefing_2026-08-01.md",
    )
  })

  it("ignores trailing separators instead of returning an empty name", () => {
    expect(basename("a/b/")).toBe("b")
    expect(basename("a/b///")).toBe("b")
    expect(basename("a\\b\\")).toBe("b")
  })

  it("falls back to the input rather than an empty name (boundary)", () => {
    expect(basename("/")).toBe("/")
    expect(basename("")).toBe("")
  })
})
