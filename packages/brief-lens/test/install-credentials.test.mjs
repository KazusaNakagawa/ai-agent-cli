import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { dirname } from "node:path"
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"

// docker/install-claude-credentials.sh runs in the container as root before the app
// starts. It must not put a stale host export over a login the container has refreshed.
const script = new URL("../../../docker/install-claude-credentials.sh", import.meta.url).pathname
const skip = !existsSync(script) || process.platform === "win32"

const login = (marker, expiresAt) => JSON.stringify({ claudeAiOauth: { accessToken: marker, refreshToken: "r", expiresAt } })

function run({ src, dest }) {
  const dir = mkdtempSync(join(tmpdir(), "install-creds-"))
  try {
    const srcPath = join(dir, "export.json")
    const destPath = join(dir, "installed.json")
    if (src !== undefined) writeFileSync(srcPath, src)
    if (dest !== undefined) writeFileSync(destPath, dest, { mode: 0o644 })
    const res = spawnSync("sh", [script, srcPath, destPath], {
      // The script reads expiry with node, as the image does.
      env: { PATH: `${dirname(process.execPath)}:${process.env.PATH}` },
      encoding: "utf8",
    })
    return {
      status: res.status,
      output: res.stderr,
      body: existsSync(destPath) ? readFileSync(destPath, "utf8") : null,
      mode: existsSync(destPath) ? statSync(destPath).mode & 0o777 : null,
    }
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

test("installs the export when the container has no login yet, owner-only", { skip }, () => {
  const r = run({ src: login("HOST", 2000) })
  assert.equal(r.status, 0, r.output)
  assert.match(r.body, /HOST/)
  assert.equal(r.mode, 0o600)
})

test("keeps a login the container refreshed when the export expires earlier", { skip }, () => {
  const r = run({ src: login("HOST-STALE", 1000), dest: login("CONTAINER-FRESH", 5000) })
  assert.equal(r.status, 0, r.output)
  assert.match(r.body, /CONTAINER-FRESH/)
  assert.doesNotMatch(r.body, /HOST-STALE/)
  assert.match(r.output, /keeping the container's login/)
})

test("keeps the installed login when both expire at the same moment", { skip }, () => {
  const r = run({ src: login("HOST", 3000), dest: login("CONTAINER", 3000) })
  assert.match(r.body, /CONTAINER/)
})

test("a newer host export replaces the installed login", { skip }, () => {
  const r = run({ src: login("HOST-NEW", 9000), dest: login("CONTAINER-OLD", 5000) })
  assert.equal(r.status, 0, r.output)
  assert.match(r.body, /HOST-NEW/)
  assert.equal(r.mode, 0o600)
  assert.match(r.output, /newer host login/)
})

test("an unreadable installed login is replaced", { skip }, () => {
  const r = run({ src: login("HOST", 1000), dest: "not json" })
  assert.match(r.body, /HOST/)
})

test("an unreadable export never replaces a working login", { skip }, () => {
  const r = run({ src: "not json", dest: login("CONTAINER", 1000) })
  assert.match(r.body, /CONTAINER/)
})

test("without an export it keeps what is installed", { skip }, () => {
  const r = run({ dest: login("CONTAINER", 1000) })
  assert.equal(r.status, 0, r.output)
  assert.match(r.body, /CONTAINER/)
  assert.match(r.output, /keeping the login already in the container/)
})

test("with neither it explains how to export one and creates nothing", { skip }, () => {
  const r = run({})
  assert.equal(r.status, 0)
  assert.equal(r.body, null)
  assert.match(r.output, /docker\/sync-claude-auth\.sh/)
})
