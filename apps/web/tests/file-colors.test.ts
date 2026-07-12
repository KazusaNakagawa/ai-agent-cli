import { describe, expect, it } from "vitest"

import { colorForFile } from "@/lib/fileColors"

describe("colorForFile", () => {
  it("maps known extensions to their brand color (success)", () => {
    expect(colorForFile("main.py")).toBe("#3776AB")
    expect(colorForFile("index.ts")).toBe("#3178C6")
    expect(colorForFile("data.json")).toBe("#F7DF1E")
  })

  it("is case-insensitive on the extension", () => {
    expect(colorForFile("SCRIPT.PY")).toBe("#3776AB")
  })

  it("falls back to currentColor for unknown extensions (failure)", () => {
    expect(colorForFile("weird.xyz")).toBe("currentColor")
  })

  it("falls back to currentColor for a name with no extension (boundary)", () => {
    expect(colorForFile("Makefile")).toBe("currentColor")
  })
})
