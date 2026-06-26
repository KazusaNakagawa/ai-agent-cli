import { readFile } from "fs/promises"
import { NextResponse } from "next/server"
import path from "path"

const STORAGE_ROOT = path.resolve(
  process.cwd(),
  "../../apps/python/input/images"
)

const MIME: Record<string, string> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  gif: "image/gif",
  webp: "image/webp",
}

export async function GET(
  _req: Request,
  { params }: { params: { path: string[] } }
) {
  const relative = params.path.join("/")
  const resolved = path.resolve(STORAGE_ROOT, relative)

  // Path traversal guard
  if (!resolved.startsWith(STORAGE_ROOT + path.sep) && resolved !== STORAGE_ROOT) {
    return NextResponse.json({ error: "Forbidden" }, { status: 400 })
  }

  const ext = resolved.split(".").pop()?.toLowerCase() ?? ""
  const contentType = MIME[ext] ?? "application/octet-stream"

  try {
    const data = await readFile(resolved)
    return new Response(data, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    })
  } catch {
    return NextResponse.json({ error: "Not found" }, { status: 404 })
  }
}
