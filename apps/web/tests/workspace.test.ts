import { promises as fs } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

import { afterAll, beforeAll, describe, expect, it } from "vitest"

import {
  listDir,
  readFile,
  resolveWithinRoot,
  rootPathFor,
  workspaceRoots,
  writeFile,
} from "@/lib/workspace"

describe("resolveWithinRoot", () => {
  const root = "/srv/workspace"

  it("resolves a normal relative path (success)", () => {
    expect(resolveWithinRoot(root, "a/b.md")).toBe("/srv/workspace/a/b.md")
  })

  it("resolves the empty path to the root itself (boundary)", () => {
    expect(resolveWithinRoot(root, "")).toBe("/srv/workspace")
  })

  it("rejects parent-traversal paths (failure)", () => {
    expect(() => resolveWithinRoot(root, "../secret")).toThrow(/escapes/)
    expect(() => resolveWithinRoot(root, "a/../../secret")).toThrow(/escapes/)
  })

  it("rejects absolute paths (failure)", () => {
    expect(() => resolveWithinRoot(root, "/etc/passwd")).toThrow(/absolute/)
  })
})

describe("workspace roots", () => {
  let root: string

  beforeAll(async () => {
    root = await fs.mkdtemp(join(tmpdir(), "ws-roots-"))
    await fs.mkdir(join(root, "alpha"))
    await fs.mkdir(join(root, "beta"))
  })

  afterAll(async () => {
    await fs.rm(root, { recursive: true, force: true })
    delete process.env.WORKSPACE_ROOTS
  })

  it("parses WORKSPACE_ROOTS and drops non-existent paths (success/boundary)", () => {
    process.env.WORKSPACE_ROOTS = JSON.stringify([
      { id: "a", label: "Alpha", path: join(root, "alpha") },
      { id: "gone", label: "Gone", path: join(root, "does-not-exist") },
      { id: "b", label: "Beta", path: join(root, "beta") },
    ])
    expect(workspaceRoots().map((r) => r.id)).toEqual(["a", "b"])
  })

  it("resolves a known root id, falling back to the first for unknown ids", () => {
    process.env.WORKSPACE_ROOTS = JSON.stringify([
      { id: "a", label: "Alpha", path: join(root, "alpha") },
      { id: "b", label: "Beta", path: join(root, "beta") },
    ])
    expect(rootPathFor("b")).toBe(join(root, "beta"))
    expect(rootPathFor("nope")).toBe(join(root, "alpha"))
    expect(rootPathFor(null)).toBe(join(root, "alpha"))
  })
})

describe("filesystem helpers", () => {
  let root: string

  beforeAll(async () => {
    root = await fs.mkdtemp(join(tmpdir(), "ws-test-"))
    await fs.mkdir(join(root, "sub"))
    await fs.writeFile(join(root, "a.md"), "# A", "utf8")
    await fs.writeFile(join(root, "sub", "b.md"), "# B", "utf8")
  })

  afterAll(async () => {
    await fs.rm(root, { recursive: true, force: true })
  })

  it("lists directories first then files (success)", async () => {
    const entries = await listDir(root, "")
    expect(entries.map((e) => e.name)).toEqual(["sub", "a.md"])
    expect(entries[0]).toMatchObject({ type: "dir", path: "sub" })
    expect(entries[1]).toMatchObject({ type: "file", path: "a.md" })
  })

  it("reads a file's content (success)", async () => {
    expect(await readFile(root, "sub/b.md")).toBe("# B")
  })

  it("writes then reads back, creating parent dirs (success)", async () => {
    await writeFile(root, "nested/deep/c.md", "hello")
    expect(await readFile(root, "nested/deep/c.md")).toBe("hello")
  })

  it("refuses to read outside the root (failure)", async () => {
    await expect(readFile(root, "../escape.md")).rejects.toThrow(/escapes/)
  })
})
