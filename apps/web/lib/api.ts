import { readFileSync } from "node:fs"
import { join } from "node:path"

const API_BASE = process.env.API_BASE ?? "http://127.0.0.1:8000"
const TOKEN_PATH = process.env.AI_AGENT_TOKEN_PATH ?? join(process.cwd(), ".token")

function readToken(): string {
  return readFileSync(TOKEN_PATH, "utf8").trim()
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set("Authorization", `Bearer ${readToken()}`)
  // `cache: 'no-store'` opts out of Next.js's Server Component fetch cache.
  // Without it, RSC reads (e.g. /api/state) are memoised for the lifetime
  // of the render and stale after the user mutates state, so the wizard
  // would not advance to OnboardedHome on reload.
  return fetch(`${API_BASE}${path}`, { cache: "no-store", ...init, headers })
}
