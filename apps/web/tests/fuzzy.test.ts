import { describe, expect, it } from "vitest"

import { fuzzySearch, matchScore } from "@/lib/fuzzy"
import { basename } from "@/lib/utils"

describe("filename-only filtering (as used by the sidebar filter)", () => {
  const files = [
    { path: "assets/images/logo.png" },
    { path: "assets/images/icon.png" },
    { path: "src/app.py" },
    { path: "docs/notes.md" },
  ]

  it('typing an extension like "png" surfaces only files with that extension', () => {
    const results = fuzzySearch(files, "png", (f) => basename(f.path))
    expect(results.map((f) => f.path).sort()).toEqual(
      ["assets/images/icon.png", "assets/images/logo.png"].sort(),
    )
  })
})

describe("matchScore", () => {
  it("matches when query characters appear in order (success)", () => {
    expect(matchScore("wst", "workspace/FileTree.tsx")).not.toBeNull()
  })

  it("returns null when a query character is missing (failure)", () => {
    expect(matchScore("xyz", "workspace/FileTree.tsx")).toBeNull()
  })

  it("returns 0 for an empty query (boundary)", () => {
    expect(matchScore("", "anything")).toBe(0)
  })

  it("scores a path-start / post-separator match higher than a buried match", () => {
    const afterSlash = matchScore("file", "src/file.ts")
    const buried = matchScore("file", "srcxfilexts")
    expect(afterSlash).not.toBeNull()
    expect(buried).not.toBeNull()
    expect(afterSlash! > buried!).toBe(true)
  })
})

describe("fuzzySearch", () => {
  const items = [
    "components/workspace/FileTree.tsx",
    "components/workspace/FileFinder.tsx",
    "lib/fsAccess.ts",
    "lib/fuzzy.ts",
  ]

  it("filters to only subsequence matches and ranks best first (success)", () => {
    const results = fuzzySearch(items, "filetree", (s) => s)
    expect(results[0]).toBe("components/workspace/FileTree.tsx")
  })

  it("returns everything (up to limit) for an empty query (boundary)", () => {
    expect(fuzzySearch(items, "", (s) => s, 2)).toHaveLength(2)
  })

  it("returns an empty list when nothing matches (failure)", () => {
    expect(fuzzySearch(items, "zzzzz", (s) => s)).toEqual([])
  })

  it("respects the limit", () => {
    expect(fuzzySearch(items, "ts", (s) => s, 1)).toHaveLength(1)
  })
})
