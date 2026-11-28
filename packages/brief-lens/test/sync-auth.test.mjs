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

// --- paths that do not need a real Keychain or Linux ---------------------------------

import { chmodSync } from "node:fs"

const posix = existsSync(script) && process.platform !== "win32"

test("macOS branch asks the Keychain for the account even when USER is unset", { skip: !posix }, () => {
  const home = mkdtempSync(join(tmpdir(), "sync-auth-mac-"))
  try {
    const bin = join(home, "bin")
    mkdirSync(bin)
    writeFileSync(join(bin, "uname"), "#!/bin/sh\necho Darwin\n", { mode: 0o755 })
    // Succeeds only when called with -a <the real account name>, like the real item.
    const account = spawnSync("id", ["-un"], { encoding: "utf8" }).stdout.trim()
    writeFileSync(
      join(bin, "security"),
      `#!/bin/sh\ncase " $* " in *" -a ${account} "*) printf '%s' '{"claudeAiOauth":{"accessToken":"a","refreshToken":"r"}}' ;; *) exit 44 ;; esac\n`,
      { mode: 0o755 },
    )
    const out = join(home, "out")
    const res = spawnSync("bash", [script], {
      // No USER at all: under `set -u` an unguarded $USER aborts the script.
      env: { PATH: `${bin}:${process.env.PATH}`, HOME: home, BRIEF_LENS_AUTH_DIR: out },
      encoding: "utf8",
    })
    assert.equal(res.status, 0, res.stdout + res.stderr)
    assert.ok(existsSync(join(out, ".credentials.json")))
  } finally {
    rmSync(home, { recursive: true, force: true })
  }
})

test("an output directory the user cannot write explains what to do", { skip: !posix || process.getuid?.() === 0 }, () => {
  const home = mkdtempSync(join(tmpdir(), "sync-auth-ro-"))
  try {
    mkdirSync(join(home, ".claude"))
    writeFileSync(join(home, ".claude", ".credentials.json"), login())
    const out = join(home, "out")
    mkdirSync(out)
    chmodSync(out, 0o500)
    const res = spawnSync("bash", [script], {
      env: { PATH: process.env.PATH, HOME: home, BRIEF_LENS_AUTH_DIR: out },
      encoding: "utf8",
    })
    assert.equal(res.status, 1)
    assert.match(res.stderr, /cannot write/)
    assert.match(res.stderr, /before docker compose/)
    assert.ok(!res.stderr.includes(SECRET))
  } finally {
    chmodSync(join(home, "out"), 0o700)
    rmSync(home, { recursive: true, force: true })
  }
})
