// Run the Playwright e2e suite from a throwaway copy of apps/web + apps/python
// on other ports, so it can run while the developer's own `next dev` (3000)
// and FastAPI (8000) keep going. A second `next dev` in this checkout would
// share `.next` with the running one, hence the copy.
//
// Usage: npm run test:e2e:isolated [-- <playwright args>]
// Env:   E2E_WEB_PORT (default 3100), E2E_API_PORT (default 8100),
//        E2E_ISOLATED_KEEP=1 keeps the copy even when the run passes.
import { spawnSync } from "node:child_process"
import { existsSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { connect, createServer } from "node:net"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"

const repo = fileURLToPath(new URL("../../..", import.meta.url))
const webPort = process.env.E2E_WEB_PORT ?? "3100"
const apiPort = process.env.E2E_API_PORT ?? "8100"
const keep = process.env.E2E_ISOLATED_KEEP === "1"

const quote = (s) => `'${s.replaceAll("'", "'\\''")}'`

function fail(message) {
  console.error(`e2e-isolated: ${message}`)
  process.exit(1)
}

// A dev server listening on all interfaces (`*:3000`) still lets a bind to
// 127.0.0.1 succeed on macOS, so also try to connect: an answer means taken.
function canConnect(port, host) {
  return new Promise((resolve) => {
    const socket = connect({ port: Number(port), host })
    socket.once("connect", () => {
      socket.destroy()
      resolve(true)
    })
    socket.once("error", () => resolve(false))
  })
}

function canListen(port) {
  return new Promise((resolve) => {
    const server = createServer()
    server.once("error", () => resolve(false))
    server.listen(Number(port), "127.0.0.1", () => server.close(() => resolve(true)))
  })
}

async function portFree(port) {
  if ((await canConnect(port, "127.0.0.1")) || (await canConnect(port, "::1"))) return false
  return canListen(port)
}

for (const path of ["apps/web/node_modules", "apps/python/.venv"]) {
  if (!existsSync(join(repo, path))) fail(`${path} not found; install the dependencies first`)
}
for (const port of [webPort, apiPort]) {
  if (!(await portFree(port))) fail(`port ${port} is in use; set E2E_WEB_PORT / E2E_API_PORT`)
}

// Copy what git would see: tracked files with their working-tree edits, plus
// new files not yet added. Anything gitignored (personal config, input/,
// output/, tokens, build output, caches) stays behind without a list to keep
// in sync. Tracked files deleted locally are skipped.
const listed = spawnSync(
  "git",
  ["-C", repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "apps/web", "apps/python"],
  { encoding: "utf8" },
)
if (listed.status !== 0) fail(`git ls-files failed: ${listed.stderr}`)
// The dependency dirs are linked below; a checkout where they are themselves
// symlinks (a worktree) would otherwise list them as new files.
const LINKED = ["apps/web/node_modules", "apps/python/.venv"]
const files = listed.stdout
  .split("\0")
  .filter((f) => f && !LINKED.includes(f) && existsSync(join(repo, f)))

const dir = mkdtempSync(join(tmpdir(), "ai-agent-e2e-"))
const fileList = join(dir, ".e2e-files")
writeFileSync(fileList, files.join("\0"))
const copy = spawnSync(
  "sh",
  ["-c", `tar -C ${quote(repo)} --null -T ${quote(fileList)} -cf - | tar -x -C ${quote(dir)}`],
  { stdio: "inherit" },
)
if (copy.status !== 0) fail(`copying the sources into ${dir} failed`)

// Dependencies are linked, not copied: they are large and the run only reads them.
for (const path of LINKED) symlinkSync(join(repo, path), join(dir, path))

console.log(`e2e-isolated: running in ${dir} (web ${webPort}, api ${apiPort})`)
const run = spawnSync("npx", ["playwright", "test", ...process.argv.slice(2)], {
  cwd: join(dir, "apps/web"),
  stdio: "inherit",
  env: { ...process.env, E2E_WEB_PORT: webPort, E2E_API_PORT: apiPort },
})
const code = run.status ?? 1

if (code === 0 && !keep) {
  rmSync(dir, { recursive: true, force: true })
} else {
  console.log(`e2e-isolated: copy kept at ${dir} (report: ${join(dir, "apps/web/playwright-report")})`)
}
process.exit(code)
