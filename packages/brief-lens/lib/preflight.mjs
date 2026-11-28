import { accessSync, constants, statSync } from "node:fs"
import { delimiter, join } from "node:path"

// What the bundled Next.js accepts; keep in step with `engines` in package.json.
const NODE_REQUIREMENT = "18.18 or newer (19.x needs 19.8+)"

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

function isSupportedNode(version) {
  const [major, minor] = version.replace(/^v/, "").split(".").map(Number)
  if (major === 18) return minor >= 18
  if (major === 19) return minor >= 8
  return major >= 20
}

/** Check prerequisites; returns human-readable problems (empty = all good). */
export function preflight({ env, nodeVersion }) {
  const problems = []
  if (!isSupportedNode(nodeVersion)) {
    problems.push(`Node.js ${NODE_REQUIREMENT} is required (found ${nodeVersion}).`)
  }
  for (const tool of TOOLS) {
    if (!findOnPath(tool.name, env)) {
      problems.push(`\`${tool.name}\` not found on PATH — ${tool.why}.\n    Install: ${tool.hint}`)
    }
  }
  return problems
}
