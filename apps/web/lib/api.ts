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
  return fetch(`${API_BASE}${path}`, { ...init, headers })
}
