import { apiFetch } from "@/lib/api"

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "host",
  "content-length",
])

async function handle(
  req: Request,
  { params }: { params: { path: string[] } },
) {
  const upstreamPath = "/api/" + params.path.join("/")
  const url = new URL(req.url)
  const target = upstreamPath + url.search

  const init: RequestInit = { method: req.method }
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer()
    const ct = req.headers.get("content-type")
    if (ct) init.headers = { "content-type": ct }
  }

  const upstream = await apiFetch(target, init)

  const headers = new Headers()
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value)
  })
  // Stop the browser's HTTP cache from serving stale `/api/run/{id}` polls
  // and similarly stop Next.js from caching the GET route handler itself.
  // Override whatever upstream sent (FastAPI sets no cache headers).
  headers.set("Cache-Control", "no-store, no-cache, must-revalidate")
  headers.set("Pragma", "no-cache")

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  })
}

// Force the proxy out of Next.js's static cache so every request hits FastAPI.
export const dynamic = "force-dynamic"

export {
  handle as GET,
  handle as POST,
  handle as PUT,
  handle as DELETE,
  handle as PATCH,
}
