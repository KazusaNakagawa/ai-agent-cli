import path from "path"

/**
 * Root directory for uploaded images and attachments (server-only).
 *
 * `AI_AGENT_INPUT_DIR` wins when set, so the standalone server — whose cwd is
 * `.next/standalone`, not `apps/web` — stores uploads in the data home the
 * launcher chose. Unset keeps the dev layout: `apps/python/input` resolved
 * from the `apps/web` cwd. (`__dirname` is unusable here: in production it
 * points into `.next/server/`.)
 */
export function inputRoot(
  env: Record<string, string | undefined> = process.env,
  cwd: string = process.cwd(),
): string {
  const override = env.AI_AGENT_INPUT_DIR?.trim()
  if (override) return path.resolve(cwd, override)
  return path.resolve(cwd, "../../apps/python/input")
}
