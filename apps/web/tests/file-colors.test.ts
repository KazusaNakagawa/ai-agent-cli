import { describe, expect, it } from "vitest"

import { colorForFile, languageForFile } from "@/lib/fileColors"

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

describe("languageForFile", () => {
  it("maps known extensions to a highlighter language id (success)", () => {
    expect(languageForFile("main.py")).toBe("python")
    expect(languageForFile("index.ts")).toBe("typescript")
    expect(languageForFile("App.tsx")).toBe("tsx")
  })

  it("is case-insensitive on the extension", () => {
    expect(languageForFile("SCRIPT.PY")).toBe("python")
  })

  it("returns null for markdown, so it renders via MarkdownView instead", () => {
    expect(languageForFile("README.md")).toBeNull()
  })

  it("returns null for unknown extensions (failure/boundary)", () => {
    expect(languageForFile("weird.xyz")).toBeNull()
    expect(languageForFile("Makefile")).toBeNull()
  })
})
