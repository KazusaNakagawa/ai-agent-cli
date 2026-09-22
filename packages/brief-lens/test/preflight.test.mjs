import assert from "node:assert/strict"
import { chmodSync, mkdirSync, writeFileSync } from "node:fs"
import { mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { delimiter, join } from "node:path"
import { test } from "node:test"

import { findOnPath, preflight } from "../lib/preflight.mjs"

function fakeBin(dir, name) {
  mkdirSync(dir, { recursive: true })
  const p = join(dir, name)
  writeFileSync(p, "#!/bin/sh\n")
  chmodSync(p, 0o755)
  return p
}

test("findOnPath finds an executable", () => {
  const dir = mkdtempSync(join(tmpdir(), "bl-pf-"))
  const p = fakeBin(dir, "uv")
  assert.equal(findOnPath("uv", { PATH: dir }), p)
})

test("findOnPath skips non-executable files and empty PATH entries", () => {
  const dir = mkdtempSync(join(tmpdir(), "bl-pf-"))
  writeFileSync(join(dir, "uv"), "")
  assert.equal(findOnPath("uv", { PATH: `${delimiter}${dir}` }), null)
})

test("findOnPath returns null with no PATH", () => {
  assert.equal(findOnPath("uv", {}), null)
})

test("preflight passes when everything is present", () => {
  const dir = mkdtempSync(join(tmpdir(), "bl-pf-"))
  fakeBin(dir, "uv")
  fakeBin(dir, "claude")
  assert.deepEqual(preflight({ env: { PATH: dir }, nodeVersion: "v24.1.0" }), [])
})

test("preflight reports each missing tool with an install hint", () => {
  const problems = preflight({ env: { PATH: "" }, nodeVersion: "v24.1.0" })
  assert.equal(problems.length, 2)
  assert.match(problems[0], /uv.*not found/s)
  assert.match(problems[0], /astral\.sh\/uv/)
  assert.match(problems[1], /claude.*not found/s)
  assert.match(problems[1], /claude-code/)
})

test("preflight rejects Node older than 18 and accepts exactly 18", () => {
  const dir = mkdtempSync(join(tmpdir(), "bl-pf-"))
  fakeBin(dir, "uv")
  fakeBin(dir, "claude")
  assert.match(preflight({ env: { PATH: dir }, nodeVersion: "v17.9.1" })[0], /Node\.js 18/)
  assert.deepEqual(preflight({ env: { PATH: dir }, nodeVersion: "v18.0.0" }), [])
})
