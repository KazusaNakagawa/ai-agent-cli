#!/usr/bin/env node
// Entry point for `npx brief-lens`: pre-flight → data home → Python venv → serve.
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { fileURLToPath } from "node:url"

import { HELP, parseCliArgs, UsageError } from "../lib/args.mjs"
import { ensureHome } from "../lib/home.mjs"
import { resolveLayout } from "../lib/layout.mjs"
import { preflight } from "../lib/preflight.mjs"
import { ensureVenv } from "../lib/python.mjs"
import { runCommand, serve } from "../lib/serve.mjs"

const pkgRoot = fileURLToPath(new URL("..", import.meta.url))
const log = (msg) => console.log(msg)

async function main() {
  let opts
  try {
    opts = parseCliArgs(process.argv.slice(2), process.env)
  } catch (err) {
    if (err instanceof UsageError) {
      console.error(`brief-lens: ${err.message}\nTry: brief-lens --help`)
      return 2
    }
    throw err
  }
  if (opts.help) {
    process.stdout.write(HELP)
    return 0
  }
  if (opts.version) {
    log(JSON.parse(readFileSync(join(pkgRoot, "package.json"), "utf8")).version)
    return 0
  }

  const problems = preflight({ env: process.env, nodeVersion: process.version })
  if (problems.length > 0) {
    console.error(`brief-lens: missing prerequisites:\n\n${problems.map((p) => `  - ${p}`).join("\n")}`)
    return 1
  }

  const layout = resolveLayout(pkgRoot)
  const { created, tokenPath } = ensureHome(opts.home, join(layout.pythonDir, "config"))
  if (created.includes("config/briefing.json")) {
    log(`Created ${join(opts.home, "config", "briefing.json")} from the template — edit it (or use the Config screen) to describe your portfolio.`)
  }
  const { uvicorn } = await ensureVenv({ home: opts.home, appDir: layout.pythonDir, run: runCommand, log })
  return serve({ layout, opts, uvicorn, tokenPath, log })
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(`brief-lens: ${err.message}`)
    process.exit(1)
  },
)
