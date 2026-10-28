import { createHash } from "node:crypto"
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"

// Matches requires-python in apps/python/pyproject.toml.
const PYTHON_SPEC = ">=3.11,<3.14"

export function venvPaths(home) {
  const venv = join(home, "runtime", "venv")
  return {
    venv,
    bin: join(venv, "bin"),
    python: join(venv, "bin", "python"),
    uvicorn: join(venv, "bin", "uvicorn"),
    stamp: join(home, "runtime", "requirements.sha256"),
  }
}

/**
 * Make sure the backend venv exists and matches requirements.txt.
 *
 * The lock's hash is stamped after a successful sync; a matching stamp plus an
 * existing uvicorn means nothing to do. The stamp is removed before syncing so
 * an interrupted install is retried on the next run.
 */
export async function ensureVenv({ home, appDir, run, log }) {
  const p = venvPaths(home)
  const lock = join(appDir, "requirements.txt")
  const hash = createHash("sha256").update(readFileSync(lock)).digest("hex")

  const stamped = existsSync(p.stamp) ? readFileSync(p.stamp, "utf8").trim() : null
  if (stamped === hash && existsSync(p.uvicorn)) return { installed: false, ...p }

  rmSync(p.stamp, { force: true })
  if (!existsSync(p.python)) {
    log("Creating Python environment (first run)...")
    await run("uv", ["venv", p.venv, "--python", PYTHON_SPEC])
  }
  log("Installing Python dependencies — this can take a few minutes the first time...")
  await run("uv", ["pip", "sync", lock, "--python", p.python])
  writeFileSync(p.stamp, hash + "\n")
  return { installed: true, ...p }
}
