import assert from "node:assert/strict"
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"

import { ensureHome } from "../lib/home.mjs"

function examples() {
  const dir = mkdtempSync(join(tmpdir(), "bl-ex-"))
  writeFileSync(join(dir, "briefing.json.example"), '{"example": true}\n')
  writeFileSync(join(dir, "holdings.json.example"), "{}\n")
  return dir
}

test("first run creates the layout, seeds briefing.json and a 0600 token", () => {
  const home = join(mkdtempSync(join(tmpdir(), "bl-home-")), "nested", ".brief-lens")
  const result = ensureHome(home, examples())

  for (const d of ["config", "output", "log", "input", "runtime"]) {
    assert.ok(statSync(join(home, d)).isDirectory(), d)
  }
  assert.equal(readFileSync(join(home, "config", "briefing.json"), "utf8"), '{"example": true}\n')
  // Optional feature configs are not seeded: their absence disables the feature.
  assert.equal(existsSync(join(home, "config", "holdings.json")), false)

  const token = readFileSync(join(home, "session-token"), "utf8").trim()
  assert.ok(token.length >= 40, "token should carry 32 random bytes")
  assert.equal(statSync(join(home, "session-token")).mode & 0o777, 0o600)
  assert.deepEqual(result.created, ["config/briefing.json", "session-token"])
})

test("second run keeps an edited config and the existing token", () => {
  const home = mkdtempSync(join(tmpdir(), "bl-home-"))
  const ex = examples()
  ensureHome(home, ex)
  writeFileSync(join(home, "config", "briefing.json"), '{"mine": true}\n')
  const token = readFileSync(join(home, "session-token"), "utf8")

  const result = ensureHome(home, ex)
  assert.equal(readFileSync(join(home, "config", "briefing.json"), "utf8"), '{"mine": true}\n')
  assert.equal(readFileSync(join(home, "session-token"), "utf8"), token)
  assert.deepEqual(result.created, [])
})

test("an empty token file is regenerated", () => {
  const home = mkdtempSync(join(tmpdir(), "bl-home-"))
  mkdirSync(home, { recursive: true })
  writeFileSync(join(home, "session-token"), "\n")
  const result = ensureHome(home, examples())
  assert.ok(readFileSync(join(home, "session-token"), "utf8").trim().length > 0)
  assert.ok(result.created.includes("session-token"))
})

test("a missing template fails loudly", () => {
  const home = mkdtempSync(join(tmpdir(), "bl-home-"))
  const empty = mkdtempSync(join(tmpdir(), "bl-ex-"))
  assert.throws(() => ensureHome(home, empty), /briefing\.json\.example/)
})

test("a regenerated token over a world-readable empty file ends up 0600", () => {
  const home = mkdtempSync(join(tmpdir(), "bl-home-"))
  const tokenPath = join(home, "session-token")
  writeFileSync(tokenPath, "")
  chmodSync(tokenPath, 0o644)
  ensureHome(home, examples())
  assert.equal(statSync(tokenPath).mode & 0o777, 0o600)
})

test("an existing token with loose permissions is tightened, not replaced", () => {
  const home = mkdtempSync(join(tmpdir(), "bl-home-"))
  const tokenPath = join(home, "session-token")
  writeFileSync(tokenPath, "keep-me\n")
  chmodSync(tokenPath, 0o644)
  const result = ensureHome(home, examples())
  assert.equal(readFileSync(tokenPath, "utf8"), "keep-me\n")
  assert.equal(statSync(tokenPath).mode & 0o777, 0o600)
  assert.deepEqual(result.created, ["config/briefing.json"])
})
