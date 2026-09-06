import { describe, expect, it } from "vitest"

import {
  colorForFile,
  isBinaryFile,
  isEnvFile,
  isImageFile,
  isLogFile,
  isPdfFile,
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

describe("isPdfFile", () => {
  it("matches .pdf (success)", () => {
    expect(isPdfFile("report.pdf")).toBe(true)
  })

  it("is case-insensitive on the extension (boundary)", () => {
    expect(isPdfFile("REPORT.PDF")).toBe(true)
  })

  it("rejects non-pdf extensions (failure)", () => {
    expect(isPdfFile("notes.md")).toBe(false)
    expect(isPdfFile("photo.png")).toBe(false)
  })

  it("does not match a name that merely contains 'pdf' (boundary)", () => {
    expect(isPdfFile("pdf")).toBe(false)
    expect(isPdfFile("report.pdf.bak")).toBe(false)
    expect(isPdfFile("mypdf.txt")).toBe(false)
  })
})

describe("isBinaryFile", () => {
  it("covers images and PDFs, which have dedicated viewers (success)", () => {
    expect(isBinaryFile("photo.png")).toBe(true)
    expect(isBinaryFile("report.pdf")).toBe(true)
  })

  it("covers binaries with no viewer, so they are never decoded as text (success)", () => {
    for (const ext of ["zip", "gz", "xlsx", "docx", "woff2", "mp4", "sqlite"]) {
      expect(isBinaryFile(`blob.${ext}`)).toBe(true)
    }
  })

  it("rejects text formats so they keep the editable path (failure)", () => {
    for (const name of ["notes.md", "main.py", "index.ts", "data.json", "app.log", ".env"]) {
      expect(isBinaryFile(name)).toBe(false)
    }
  })

  it("treats an extensionless name as text (boundary)", () => {
    expect(isBinaryFile("Makefile")).toBe(false)
    expect(isBinaryFile("LICENSE")).toBe(false)
  })

  it("is case-insensitive on the extension (boundary)", () => {
    expect(isBinaryFile("ARCHIVE.ZIP")).toBe(true)
  })
})
