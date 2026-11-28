import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"

// docker/sync-claude-auth.sh reads ~/.claude/.credentials.json on Linux and the
// Keychain on macOS, so these tests only make sense on Linux with python3.
const script = new URL("../../../docker/sync-claude-auth.sh", import.meta.url).pathname
const hasPython = spawnSync("python3", ["--version"]).status === 0
const skip = process.platform !== "linux" || !existsSync(script) || !hasPython

const SECRET = "SECRET-ACCESS-TOKEN-VALUE"

function run(credentials) {
  const home = mkdtempSync(join(tmpdir(), "sync-auth-"))
  try {
    if (credentials !== undefined) {
      mkdirSync(join(home, ".claude"))
      writeFileSync(join(home, ".claude", ".credentials.json"), credentials)
    }
    const out = join(home, "out")
    const res = spawnSync("bash", [script], {
      env: { PATH: process.env.PATH, HOME: home, BRIEF_LENS_AUTH_DIR: out },
      encoding: "utf8",
    })
    const file = join(out, ".credentials.json")
    return {
      status: res.status,
      output: res.stdout + res.stderr,
      copied: existsSync(file),
      mode: existsSync(file) ? statSync(file).mode & 0o777 : null,
      dirMode: existsSync(out) ? statSync(out).mode & 0o777 : null,
      body: existsSync(file) ? readFileSync(file, "utf8") : null,
    }
  } finally {
    rmSync(home, { recursive: true, force: true })
  }
}

const login = (extra = {}) =>
  JSON.stringify({ claudeAiOauth: { accessToken: SECRET, refreshToken: "r", expiresAt: Date.now() + 3_600_000, ...extra } })

test("copies a valid login with owner-only modes and never prints the token", { skip }, () => {
  const r = run(login())
  assert.equal(r.status, 0, r.output)
  assert.equal(r.mode, 0o600)
  assert.equal(r.dirMode, 0o700)
  assert.ok(r.body.includes(SECRET))
  assert.ok(!r.output.includes(SECRET))
})

test("an expired access token is copied with a warning", { skip }, () => {
  const r = run(login({ expiresAt: 1000 }))
  assert.equal(r.status, 0, r.output)
  assert.equal(r.copied, true)
  assert.match(r.output, /expired/)
})

test("refuses a login without a refresh token", { skip }, () => {
  const r = run(JSON.stringify({ claudeAiOauth: { accessToken: SECRET } }))
  assert.equal(r.status, 1)
  assert.equal(r.copied, false)
  assert.ok(!r.output.includes(SECRET))
})

test("refuses malformed JSON", { skip }, () => {
  const r = run("not json")
  assert.equal(r.status, 1)
  assert.equal(r.copied, false)
})

test("fails with guidance when there is no login at all", { skip }, () => {
  const r = run(undefined)
  assert.equal(r.status, 1)
  assert.match(r.output, /Run `claude` once/)
  assert.equal(r.copied, false)
})
