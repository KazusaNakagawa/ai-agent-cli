import assert from "node:assert/strict"
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"

import { ensureVenv, venvPaths } from "../lib/python.mjs"

function fixture() {
  const home = mkdtempSync(join(tmpdir(), "bl-py-"))
  const appDir = mkdtempSync(join(tmpdir(), "bl-app-"))
  writeFileSync(join(appDir, "requirements.txt"), "fastapi==1.0\n")
  return { home, appDir }
}

// Fake runner: records the commands and creates the files a real `uv venv`
// (python) and `uv pip sync` (uvicorn) would.
function recorder(home) {
  const calls = []
  const run = async (cmd, args) => {
    calls.push([cmd, ...args].join(" "))
    const { bin } = venvPaths(home)
    mkdirSync(bin, { recursive: true })
    writeFileSync(join(bin, args[0] === "venv" ? "python" : "uvicorn"), "")
  }
  return { calls, run }
}

test("first run creates the venv and syncs requirements", async () => {
  const { home, appDir } = fixture()
  const r = recorder(home)
  const result = await ensureVenv({ home, appDir, run: r.run, log: () => {} })
  assert.equal(result.installed, true)
  assert.equal(r.calls.length, 2)
  assert.match(r.calls[0], /^uv venv .*runtime\/venv --python >=3\.11,<3\.14$/)
  assert.match(r.calls[1], /^uv pip sync .*requirements\.txt --python .*runtime\/venv\/bin\/python$/)
})

test("second run with the same lock skips the install", async () => {
  const { home, appDir } = fixture()
  await ensureVenv({ home, appDir, run: recorder(home).run, log: () => {} })
  const r = recorder(home)
  const result = await ensureVenv({ home, appDir, run: r.run, log: () => {} })
  assert.equal(result.installed, false)
  assert.deepEqual(r.calls, [])
})

test("a changed lock re-syncs without recreating the venv", async () => {
  const { home, appDir } = fixture()
  await ensureVenv({ home, appDir, run: recorder(home).run, log: () => {} })
  writeFileSync(join(appDir, "requirements.txt"), "fastapi==2.0\n")
  const r = recorder(home)
  const result = await ensureVenv({ home, appDir, run: r.run, log: () => {} })
  assert.equal(result.installed, true)
  assert.equal(r.calls.length, 1)
  assert.match(r.calls[0], /^uv pip sync /)
})

test("a failed install leaves no stamp, so the next run retries", async () => {
  const { home, appDir } = fixture()
  const failing = async (cmd, args) => {
    if (args[0] === "pip") throw new Error("network down")
  }
  await assert.rejects(ensureVenv({ home, appDir, run: failing, log: () => {} }), /network down/)
  const r = recorder(home)
  const result = await ensureVenv({ home, appDir, run: r.run, log: () => {} })
  assert.equal(result.installed, true)
})
