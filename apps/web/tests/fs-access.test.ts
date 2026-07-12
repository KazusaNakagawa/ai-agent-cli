import { describe, expect, it } from "vitest"

import { sortChildren, type DirChild } from "@/lib/fsAccess"

// A minimal stand-in for a handle; sortChildren only reads name/kind.
function child(name: string, kind: "file" | "directory"): DirChild {
  return { name, kind, handle: { name, kind } as unknown as FileSystemHandle }
}

describe("sortChildren", () => {
  it("puts directories before files (success)", () => {
    const sorted = sortChildren([
      child("readme.md", "file"),
      child("src", "directory"),
    ])
    expect(sorted.map((c) => c.name)).toEqual(["src", "readme.md"])
  })

  it("sorts alphabetically within a kind, case-insensitively", () => {
    const sorted = sortChildren([
      child("Zeta", "directory"),
      child("alpha", "directory"),
      child("b.txt", "file"),
      child("A.txt", "file"),
    ])
    expect(sorted.map((c) => c.name)).toEqual(["alpha", "Zeta", "A.txt", "b.txt"])
  })

  it("returns an empty list unchanged (boundary)", () => {
    expect(sortChildren([])).toEqual([])
  })
})
