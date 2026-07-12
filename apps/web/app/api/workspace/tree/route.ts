import { NextResponse } from "next/server"

import { listDir, workspaceRoot } from "@/lib/workspace"

// GET /api/workspace/tree?path=<relDir> — list the immediate children of a
// directory within the workspace root. `path` defaults to the root.
export async function GET(req: Request) {
  const url = new URL(req.url)
  const relDir = url.searchParams.get("path") ?? ""
  try {
    const entries = await listDir(workspaceRoot(), relDir)
    return NextResponse.json({ entries }, { headers: { "Cache-Control": "no-store" } })
  } catch (err) {
    const message = err instanceof Error ? err.message : "failed to list directory"
    const status = /escapes|absolute/.test(message) ? 400 : 404
    return NextResponse.json({ error: message }, { status })
  }
}

export const dynamic = "force-dynamic"
