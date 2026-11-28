import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"
import { test } from "node:test"

// Guards for the Docker setup at the repository root (compose.yaml, Dockerfile).
// Not part of the published package, so skip when run outside a checkout.
const root = new URL("../../../", import.meta.url)
const composePath = new URL("compose.yaml", root)
const dockerfilePath = new URL("Dockerfile", root)
const skip = !existsSync(composePath) || !existsSync(dockerfilePath)

test("compose publishes ports to the host loopback only", { skip }, () => {
  const lines = readFileSync(composePath, "utf8").split("\n")
  const start = lines.findIndex((l) => /^\s+ports:\s*$/.test(l))
  assert.notEqual(start, -1, "compose.yaml must declare ports")
  const ports = []
  for (const line of lines.slice(start + 1)) {
    const m = line.match(/^\s+-\s+"?([^"\s]+)"?\s*$/)
    if (!m) break
    ports.push(m[1])
  }
  assert.ok(ports.length > 0)
  for (const p of ports) assert.match(p, /^127\.0\.0\.1:/, `${p} must bind 127.0.0.1`)
})

test("compose and Dockerfile do not carry an API key or a credentials file", { skip }, () => {
  for (const path of [composePath, dockerfilePath]) {
    const text = readFileSync(path, "utf8")
    // Mentions in comments are explanations; check only instruction lines.
    const code = text.split("\n").filter((l) => !l.trim().startsWith("#")).join("\n")
    assert.doesNotMatch(code, /ANTHROPIC_API_KEY/, `${path.pathname} must not pass the API key`)
    assert.doesNotMatch(code, /\.credentials\.json/, `${path.pathname} must not bake credentials`)
  }
})

test("the credentials mount is read-only", { skip }, () => {
  assert.match(readFileSync(composePath, "utf8"), /:\/run\/claude-auth:ro\s*$/m)
})

test("the app runs as a non-root user without capabilities", { skip }, () => {
  const entrypoint = readFileSync(new URL("docker/entrypoint.sh", root), "utf8")
  assert.match(entrypoint, /setpriv\s[^\n]*--reuid="\$APP_USER"/)
  assert.match(entrypoint, /--bounding-set=-all/)
  assert.match(entrypoint, /--no-new-privs/)
  assert.match(entrypoint, /^APP_USER=node$/m)
})

test("compose adds back only the capabilities the entrypoint needs", { skip }, () => {
  const text = readFileSync(composePath, "utf8")
  assert.match(text, /cap_drop:\s*\n\s+- ALL/)
  const added = [...text.matchAll(/^\s+cap_add:\s*\n((?:\s+- \w+\n)+)/gm)].flatMap((m) => m[1].match(/\w+/g))
  assert.deepEqual(added.sort(), ["CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID"])
})
