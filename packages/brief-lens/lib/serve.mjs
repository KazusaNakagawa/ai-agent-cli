import { spawn } from "node:child_process"
import { join } from "node:path"
import { createServer } from "node:net"

/** Run a command to completion with inherited stdio; reject on failure. */
export function runCommand(cmd, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: "inherit", ...options })
    child.on("error", reject)
    child.on("exit", (code, signal) => {
      if (code === 0) resolve()
      else reject(new Error(`${cmd} ${args.join(" ")} failed (${signal ?? `exit ${code}`})`))
    })
  })
}

/** Resolve true when nothing is listening on 127.0.0.1:port. */
export function isPortFree(port) {
  return new Promise((resolve) => {
    const srv = createServer()
    srv.once("error", () => resolve(false))
    srv.once("listening", () => srv.close(() => resolve(true)))
    srv.listen(port, "127.0.0.1")
  })
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

/** Poll url until it answers 2xx/3xx; fail fast if the child process dies. */
async function waitForHttp(url, child, label, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`${label} exited before it was ready (see its output above)`)
    }
    try {
      const res = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(1000) })
      if (res.status < 400) return
    } catch {
      // not up yet
    }
    await sleep(300)
  }
  throw new Error(`${label} did not answer ${url} within ${timeoutMs / 1000}s`)
}

function openBrowser(url) {
  const cmd = process.platform === "darwin" ? "open" : process.platform === "linux" ? "xdg-open" : null
  if (!cmd) return
  const child = spawn(cmd, [url], { stdio: "ignore", detached: true })
  child.on("error", () => {}) // best effort: no opener installed is fine
  child.unref()
}

/**
 * Start the API and the web server, wait until both answer, open the browser,
 * and stay up until Ctrl-C or until either process dies (which stops the other).
 * Resolves with the exit code the launcher should use.
 */
export async function serve({ layout, opts, uvicorn, tokenPath, log }) {
  for (const [flag, port] of [["--api-port", opts.apiPort], ["--port", opts.port]]) {
    if (!(await isPortFree(port))) {
      throw new Error(`port ${port} is already in use — pick another with ${flag} <n>`)
    }
  }

  const apiUrl = `http://127.0.0.1:${opts.apiPort}`
  const webUrl = `http://localhost:${opts.port}`

  const api = spawn(uvicorn, ["web.app:app", "--host", "127.0.0.1", "--port", String(opts.apiPort)], {
    cwd: layout.pythonDir,
    stdio: "inherit",
    env: { ...process.env, BRIEF_LENS_HOME: opts.home },
  })
  const web = spawn(process.execPath, ["server.js"], {
    cwd: layout.webDir,
    stdio: "inherit",
    env: {
      ...process.env,
      NODE_ENV: "production",
      PORT: String(opts.port),
      HOSTNAME: "127.0.0.1",
      API_BASE: apiUrl,
      AI_AGENT_TOKEN_PATH: tokenPath,
      AI_AGENT_INPUT_DIR: join(opts.home, "input"),
    },
  })
  const children = [api, web]

  let stopping = false
  const stop = () => {
    if (stopping) return
    stopping = true
    for (const c of children) if (c.exitCode === null && c.signalCode === null) c.kill("SIGTERM")
  }
  const exited = Promise.all(children.map((c) => new Promise((r) => c.once("exit", r))))

  process.once("SIGINT", stop)
  process.once("SIGTERM", stop)

  let unexpected = false
  for (const c of children) {
    c.once("exit", () => {
      if (!stopping) {
        unexpected = true
        stop()
      }
    })
  }

  try {
    await waitForHttp(`${apiUrl}/api/health`, api, "API server", 60_000)
    await waitForHttp(`http://127.0.0.1:${opts.port}/`, web, "web server", 60_000)
  } catch (err) {
    stop()
    await exited
    throw err
  }

  log(`\nbrief-lens is running:\n  Web UI:    ${webUrl}\n  API:       ${apiUrl}\n  Data home: ${opts.home}\nPress Ctrl-C to stop.\n`)
  if (opts.browser) openBrowser(webUrl)

  await exited
  return unexpected ? 1 : 0
}
