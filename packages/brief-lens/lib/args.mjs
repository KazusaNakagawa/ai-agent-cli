import { homedir } from "node:os"
import { join, resolve } from "node:path"
import { parseArgs } from "node:util"

export class UsageError extends Error {}

export const HELP = `Usage: brief-lens [options]

Start the brief-lens Web UI: a local API (FastAPI) and the web app (Next.js).
The first run creates the data home and installs Python dependencies with uv.

Options:
  --port <n>       Web UI port (default: 3000)
  --api-port <n>   API port (default: 8000)
  --host <addr>    Address the Web UI binds to (default: $BRIEF_LENS_HOST or 127.0.0.1).
                   The API always stays on 127.0.0.1. Anything other than a loopback
                   address makes the Web UI reachable from other machines.
  --home <dir>     Data home (default: $BRIEF_LENS_HOME or ~/.brief-lens)
  --no-browser     Do not open the browser (also skipped when $CI is set)
  -v, --version    Print the version and exit
  -h, --help       Show this help and exit

Requires Node.js 18.18+ (19.x: 19.8+), uv, and a logged-in claude CLI (paid Claude plan).
`

function parsePort(name, raw) {
  if (!/^\d+$/.test(raw ?? "")) throw new UsageError(`--${name} must be an integer, got ${JSON.stringify(raw)}`)
  const n = Number(raw)
  if (n < 1 || n > 65535) throw new UsageError(`--${name} must be between 1 and 65535, got ${n}`)
  return n
}

const DEFAULT_HOST = "127.0.0.1"

function parseHost(raw) {
  const host = raw.trim()
  if (!host || /\s/.test(host)) throw new UsageError(`--host must be an address, got ${JSON.stringify(raw)}`)
  return host
}

/** True for addresses that only this machine can reach. */
export function isLoopbackHost(host) {
  return host === "localhost" || host === "::1" || /^127\./.test(host)
}

function expandHome(p) {
  if (p === "~") return homedir()
  if (p.startsWith("~/")) return join(homedir(), p.slice(2))
  return resolve(p)
}

/** Parse argv (without node and script) into launcher options. */
export function parseCliArgs(argv, env) {
  let parsed
  try {
    parsed = parseArgs({
      args: argv,
      allowPositionals: false,
      strict: true,
      options: {
        port: { type: "string" },
        "api-port": { type: "string" },
        host: { type: "string" },
        home: { type: "string" },
        "no-browser": { type: "boolean", default: false },
        version: { type: "boolean", short: "v", default: false },
        help: { type: "boolean", short: "h", default: false },
      },
    })
  } catch (err) {
    throw new UsageError(err.message)
  }
  const v = parsed.values
  const port = parsePort("port", v.port ?? "3000")
  const apiPort = parsePort("api-port", v["api-port"] ?? "8000")
  if (port === apiPort) throw new UsageError(`--port and --api-port must differ (both ${port})`)

  const host = parseHost(v.host ?? (env.BRIEF_LENS_HOST?.trim() || DEFAULT_HOST))

  const homeRaw = v.home ?? (env.BRIEF_LENS_HOME?.trim() || join(homedir(), ".brief-lens"))
  return {
    port,
    apiPort,
    host,
    home: expandHome(homeRaw),
    browser: !v["no-browser"] && !env.CI,
    version: v.version,
    help: v.help,
  }
}
