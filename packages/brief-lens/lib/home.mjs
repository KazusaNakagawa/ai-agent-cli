import { randomBytes } from "node:crypto"
import { chmodSync, copyFileSync, existsSync, lstatSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

const DIRS = ["config", "output", "log", "input", "runtime"]

// Hold personal data; the backend expects them to be owner-only
// (apps/python/src/private_files.py).
const PRIVATE_DIRS = new Set(["input", "output"])

// Only briefing.json is required to boot. The other templates (holdings,
// money rules, self-agent profile) back optional features that stay off
// until the user creates the file.
const REQUIRED_CONFIGS = ["briefing.json"]

function hasToken(path) {
  return existsSync(path) && readFileSync(path, "utf8").trim().length > 0
}

/**
 * Create the data home layout, seed required configs from the shipped
 * templates, and make sure a session token exists (mode 0600). Never
 * overwrites user files — except an empty or whitespace-only session-token,
 * which carries no value and is regenerated. Personal directories and configs
 * are created owner-only; existing ones keep their mode (the backend warns).
 * Returns the home-relative paths it created.
 */
export function ensureHome(home, exampleDir) {
  const created = []
  for (const d of DIRS) {
    const dir = join(home, d)
    // mkdirSync returns undefined when the directory already existed. chmod
    // rather than `mode`, which the umask would filter.
    const isNew = mkdirSync(dir, { recursive: true }) !== undefined
    if (isNew && PRIVATE_DIRS.has(d)) chmodSync(dir, 0o700)
  }

  for (const name of REQUIRED_CONFIGS) {
    const target = join(home, "config", name)
    if (existsSync(target)) continue
    const template = join(exampleDir, `${name}.example`)
    if (!existsSync(template)) throw new Error(`template not found: ${template}`)
    copyFileSync(template, target)
    // The copy inherits the packaged template's mode, usually 0644.
    chmodSync(target, 0o600)
    created.push(`config/${name}`)
  }

  // Same shape as the backend's secrets.token_urlsafe(32), so either side can
  // create it. Written here first so the API and web proxy agree from boot.
  const tokenPath = join(home, "session-token")
  // Writing or chmod-ing through a symlink would touch its target instead of
  // the token, so refuse rather than follow one.
  if (lstatSync(tokenPath, { throwIfNoEntry: false })?.isSymbolicLink()) {
    throw new Error(`${tokenPath} is a symlink — remove it and run again`)
  }
  if (!hasToken(tokenPath)) {
    writeFileSync(tokenPath, randomBytes(32).toString("base64url") + "\n", { mode: 0o600 })
    created.push("session-token")
  }
  // `mode` only applies when the file is created, so enforce it explicitly:
  // an existing (regenerated or kept) token must not stay world-readable.
  chmodSync(tokenPath, 0o600)
  return { created, tokenPath }
}
