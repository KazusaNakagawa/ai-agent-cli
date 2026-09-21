import assert from "node:assert/strict"
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"

import { resolveLayout } from "../lib/layout.mjs"

function touch(p) {
  mkdirSync(join(p, ".."), { recursive: true })
  writeFileSync(p, "")
}

test("prefers the bundled dist/ layout of a published package", () => {
  const pkg = mkdtempSync(join(tmpdir(), "bl-pkg-"))
  touch(join(pkg, "dist", "python", "web", "app.py"))
  touch(join(pkg, "dist", "web", "server.js"))
  assert.deepEqual(resolveLayout(pkg), {
    pythonDir: join(pkg, "dist", "python"),
    webDir: join(pkg, "dist", "web"),
    source: "bundle",
  })
})

test("falls back to the repo checkout (packages/brief-lens → apps/)", () => {
  const repo = mkdtempSync(join(tmpdir(), "bl-repo-"))
  const pkg = join(repo, "packages", "brief-lens")
  mkdirSync(pkg, { recursive: true })
  touch(join(repo, "apps", "python", "web", "app.py"))
  touch(join(repo, "apps", "web", ".next", "standalone", "server.js"))
  assert.deepEqual(resolveLayout(pkg), {
    pythonDir: join(repo, "apps", "python"),
    webDir: join(repo, "apps", "web", ".next", "standalone"),
    source: "repo",
  })
})

test("explains how to build when the repo has no standalone build", () => {
  const repo = mkdtempSync(join(tmpdir(), "bl-repo-"))
  const pkg = join(repo, "packages", "brief-lens")
  mkdirSync(pkg, { recursive: true })
  touch(join(repo, "apps", "python", "web", "app.py"))
  assert.throws(() => resolveLayout(pkg), /npm run build/)
})

test("fails when neither layout exists", () => {
  assert.throws(() => resolveLayout(mkdtempSync(join(tmpdir(), "bl-none-"))), /cannot find/i)
})
