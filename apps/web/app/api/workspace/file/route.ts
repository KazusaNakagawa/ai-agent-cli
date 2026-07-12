import { NextResponse } from "next/server"

import { readFile, workspaceRoot, writeFile } from "@/lib/workspace"

// GET /api/workspace/file?path=<relPath> — read a UTF-8 text file.
export async function GET(req: Request) {
  const url = new URL(req.url)
  const relPath = url.searchParams.get("path")
  if (!relPath) {
    return NextResponse.json({ error: "path is required" }, { status: 400 })
  }
  try {
    const content = await readFile(workspaceRoot(), relPath)
    return NextResponse.json({ content }, { headers: { "Cache-Control": "no-store" } })
  } catch (err) {
    const message = err instanceof Error ? err.message : "failed to read file"
    const status = /escapes|absolute/.test(message) ? 400 : 404
    return NextResponse.json({ error: message }, { status })
  }
}

// PUT /api/workspace/file?path=<relPath> — write a UTF-8 text file.
export async function PUT(req: Request) {
  const url = new URL(req.url)
  const relPath = url.searchParams.get("path")
  if (!relPath) {
    return NextResponse.json({ error: "path is required" }, { status: 400 })
  }
  let body: { content?: unknown }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 })
  }
  if (typeof body.content !== "string") {
    return NextResponse.json({ error: "content must be a string" }, { status: 400 })
  }
  try {
    await writeFile(workspaceRoot(), relPath, body.content)
    return NextResponse.json({ ok: true })
  } catch (err) {
    const message = err instanceof Error ? err.message : "failed to write file"
    const status = /escapes|absolute/.test(message) ? 400 : 500
    return NextResponse.json({ error: message }, { status })
  }
}

export const dynamic = "force-dynamic"
