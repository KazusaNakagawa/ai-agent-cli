import { randomBytes } from "node:crypto"
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

const DIRS = ["config", "output", "log", "input", "runtime"]

// Only briefing.json is required to boot. The other templates (holdings,
// money rules, self-agent profile) back optional features that stay off
// until the user creates the file.
const REQUIRED_CONFIGS = ["briefing.json"]

function hasToken(path) {
  return existsSync(path) && readFileSync(path, "utf8").trim().length > 0
}

/**
 * Create the data home layout, seed required configs from the shipped
 * templates, and make sure a session token exists. Never overwrites user files.
 * Returns the home-relative paths it created.
 */
export function ensureHome(home, exampleDir) {
  const created = []
  for (const d of DIRS) mkdirSync(join(home, d), { recursive: true })

  for (const name of REQUIRED_CONFIGS) {
    const target = join(home, "config", name)
    if (existsSync(target)) continue
    const template = join(exampleDir, `${name}.example`)
    if (!existsSync(template)) throw new Error(`template not found: ${template}`)
    copyFileSync(template, target)
    created.push(`config/${name}`)
  }

  // Same shape as the backend's secrets.token_urlsafe(32), so either side can
  // create it. Written here first so the API and web proxy agree from boot.
  const tokenPath = join(home, "session-token")
  if (!hasToken(tokenPath)) {
    writeFileSync(tokenPath, randomBytes(32).toString("base64url") + "\n", { mode: 0o600 })
    created.push("session-token")
  }
  return { created, tokenPath }
}
