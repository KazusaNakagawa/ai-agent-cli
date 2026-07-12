import { NextResponse } from "next/server"

import { listDir, rootPathFor } from "@/lib/workspace"

// GET /api/workspace/tree?root=<id>&path=<relDir> — list the immediate children
// of a directory within the selected root. `path` defaults to the root itself.
export async function GET(req: Request) {
  const url = new URL(req.url)
  const relDir = url.searchParams.get("path") ?? ""
  const rootId = url.searchParams.get("root")
  try {
    const entries = await listDir(rootPathFor(rootId), relDir)
    return NextResponse.json({ entries }, { headers: { "Cache-Control": "no-store" } })
  } catch (err) {
    const message = err instanceof Error ? err.message : "failed to list directory"
    const status = /escapes|absolute/.test(message) ? 400 : 404
    return NextResponse.json({ error: message }, { status })
  }
}

export const dynamic = "force-dynamic"
