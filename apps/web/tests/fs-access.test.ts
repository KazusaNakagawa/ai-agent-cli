import { describe, expect, it } from "vitest"

import { resolveWorkspaceLink, sortChildren, type DirChild } from "@/lib/fsAccess"

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

describe("resolveWorkspaceLink", () => {
  it("resolves a same-directory relative link against the current file's path (success)", () => {
    expect(resolveWorkspaceLink("./b.md", "docs/a.md")).toBe("docs/b.md")
  })

  it("resolves a parent-directory (..) relative link (success)", () => {
    expect(resolveWorkspaceLink("../c.md", "docs/sub/a.md")).toBe("docs/c.md")
  })

  it("strips a trailing #fragment before resolving (success)", () => {
    expect(resolveWorkspaceLink("./b.md#section", "docs/a.md")).toBe("docs/b.md")
  })

  it("returns null for an absolute URL with a scheme (failure)", () => {
    expect(resolveWorkspaceLink("https://example.com/x.md", "docs/a.md")).toBeNull()
  })

  it("returns null for a mailto: link (failure)", () => {
    expect(resolveWorkspaceLink("mailto:a@example.com", "docs/a.md")).toBeNull()
  })

  it("returns null for an in-page-only anchor (boundary)", () => {
    expect(resolveWorkspaceLink("#section", "docs/a.md")).toBeNull()
  })

  it("resolves a link from a root-level file with no directory prefix (boundary)", () => {
    expect(resolveWorkspaceLink("./b.md", "a.md")).toBe("b.md")
  })

  it("returns null for a root-relative link instead of rooting it under the current directory (failure)", () => {
    expect(resolveWorkspaceLink("/foo/bar.md", "docs/a.md")).toBeNull()
  })

  it("returns null when '..' climbs above the workspace root instead of producing a malformed path (failure)", () => {
    expect(resolveWorkspaceLink("../../b.md", "docs/a.md")).toBeNull()
  })
})
