import { describe, expect, it } from "vitest"

import {
  colorForFile,
  isEnvFile,
  isImageFile,
  isLogFile,
  languageForFile,
} from "@/lib/fileColors"

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

  it("maps .env files to the ini grammar as an approximation", () => {
    expect(languageForFile(".env")).toBe("ini")
    expect(languageForFile(".env.local")).toBe("ini")
    expect(languageForFile(".env.production")).toBe("ini")
  })
})

describe("isEnvFile", () => {
  it("matches .env and its variants (success)", () => {
    expect(isEnvFile(".env")).toBe(true)
    expect(isEnvFile(".env.local")).toBe(true)
    expect(isEnvFile(".env.production")).toBe(true)
  })

  it("does not match unrelated dotfiles or names containing 'env' (failure)", () => {
    expect(isEnvFile(".envrc")).toBe(false)
    expect(isEnvFile("environment.py")).toBe(false)
    expect(isEnvFile("settings.json")).toBe(false)
  })
})

describe("isLogFile", () => {
  it("matches .log (success), rejects others (failure), case-insensitive (boundary)", () => {
    expect(isLogFile("app.log")).toBe(true)
    expect(isLogFile("APP.LOG")).toBe(true)
    expect(isLogFile("app.txt")).toBe(false)
  })
})

describe("isImageFile", () => {
  it("matches common raster/vector extensions (success)", () => {
    for (const ext of ["png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "svg"]) {
      expect(isImageFile(`photo.${ext}`)).toBe(true)
    }
  })

  it("rejects non-image extensions (failure)", () => {
    expect(isImageFile("notes.md")).toBe(false)
    expect(isImageFile("archive.zip")).toBe(false)
  })
})
