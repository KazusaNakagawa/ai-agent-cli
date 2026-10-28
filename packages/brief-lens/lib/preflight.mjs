import { accessSync, constants, statSync } from "node:fs"
import { delimiter, join } from "node:path"

const MIN_NODE_MAJOR = 18

const TOOLS = [
  {
    name: "uv",
    why: "installs and runs the Python backend",
    hint: "curl -LsSf https://astral.sh/uv/install.sh | sh   (or: brew install uv)",
  },
  {
    name: "claude",
    why: "the Claude Code CLI every agent call goes through (needs a paid Claude plan)",
    hint: "npm install -g @anthropic-ai/claude-code   then run `claude` once to log in",
  },
]

/** Return the absolute path of an executable on PATH, or null. */
export function findOnPath(name, env) {
  for (const dir of (env.PATH ?? "").split(delimiter)) {
    if (!dir) continue
    const candidate = join(dir, name)
    try {
      if (!statSync(candidate).isFile()) continue
      accessSync(candidate, constants.X_OK)
      return candidate
    } catch {
      // not here — keep looking
    }
  }
  return null
}

/** Check prerequisites; returns human-readable problems (empty = all good). */
export function preflight({ env, nodeVersion }) {
  const problems = []
  const major = Number(nodeVersion.replace(/^v/, "").split(".")[0])
  if (!(major >= MIN_NODE_MAJOR)) {
    problems.push(`Node.js ${MIN_NODE_MAJOR} or newer is required (found ${nodeVersion}).`)
  }
  for (const tool of TOOLS) {
    if (!findOnPath(tool.name, env)) {
      problems.push(`\`${tool.name}\` not found on PATH — ${tool.why}.\n    Install: ${tool.hint}`)
    }
  }
  return problems
}
