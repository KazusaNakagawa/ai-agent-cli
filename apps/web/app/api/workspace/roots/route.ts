import { NextResponse } from "next/server"

import { workspaceRoots } from "@/lib/workspace"

// GET /api/workspace/roots — the configured tree roots the user can switch
// between. Only id/label are exposed; on-disk paths stay server-side.
export async function GET() {
  const roots = workspaceRoots().map((r) => ({ id: r.id, label: r.label }))
  return NextResponse.json({ roots }, { headers: { "Cache-Control": "no-store" } })
}

export const dynamic = "force-dynamic"
