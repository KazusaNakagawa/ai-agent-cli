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

test("the credentials mount is read-only and never created by Docker", { skip }, () => {
  // Read the bind entry line by line: its keys are the lines indented deeper than
  // the `- type: bind` line, up to the next entry or key.
  const lines = readFileSync(composePath, "utf8").split("\n")
  const start = lines.findIndex((l) => l.trim() === "- type: bind")
  assert.notEqual(start, -1, "compose.yaml must declare the credentials bind mount")
  const indent = lines[start].search(/\S/)
  const entry = []
  for (const line of lines.slice(start + 1)) {
    if (line.trim() !== "" && line.search(/\S/) <= indent) break
    entry.push(line)
  }
  const block = entry.join("\n")
  assert.match(block, /target: \/run\/claude-auth\b/)
  assert.match(block, /read_only: true/)
  // A missing source must fail loudly, not become a root-owned directory.
  assert.match(block, /create_host_path: false/)
})

test("the app runs as a non-root user without capabilities", { skip }, () => {
  const entrypoint = readFileSync(new URL("docker/entrypoint.sh", root), "utf8")
  assert.match(entrypoint, /setpriv\s[^\n]*--reuid="\$APP_USER"/)
  assert.match(entrypoint, /--bounding-set=-all/)
  assert.match(entrypoint, /--no-new-privs/)
  assert.match(entrypoint, /^APP_USER=node$/m)
  // Root's HOME is /root, but the login must land in the app user's home.
  assert.match(entrypoint, /HOME="\$\(getent passwd "\$APP_USER"/)
})

test("compose adds back only the capabilities the entrypoint needs", { skip }, () => {
  const text = readFileSync(composePath, "utf8")
  assert.match(text, /cap_drop:\s*\n\s+- ALL/)
  const lines = text.split("\n")
  const start = lines.findIndex((l) => l.trim() === "cap_add:")
  assert.notEqual(start, -1, "compose.yaml must add back the capabilities the entrypoint needs")
  const added = []
  for (const line of lines.slice(start + 1)) {
    const item = line.match(/^ *- (\w+) *$/)
    if (!item) break
    added.push(item[1])
  }
  assert.deepEqual(added.sort(), ["CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID"])
})

test("the image marks itself as a container for the Web UI badge", { skip }, () => {
  assert.match(readFileSync(dockerfilePath, "utf8"), /^(ENV|\s)[^#]*\bBRIEF_LENS_RUNTIME=docker\b/m)
})

const outputOverride = new URL("compose.output.yaml", root)

test("the output override mounts only /data/output and never creates the host folder", { skip }, () => {
  const text = readFileSync(outputOverride, "utf8")
  const targets = [...text.matchAll(/^ +target: (\S+)$/gm)].map((m) => m[1])
  // /data itself holds session-token, .env and the venv.
  assert.deepEqual(targets, ["/data/output"])
  assert.match(text, /^ +create_host_path: false$/m)
})
