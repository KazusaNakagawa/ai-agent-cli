// apps/web/app/api/attachments/upload/route.ts
import { randomUUID } from "crypto"
import { mkdir, writeFile } from "fs/promises"
import { NextResponse } from "next/server"
import path from "path"

// Generic (non-image) file attachments. Images keep their own dedicated route
// (/api/images/upload) so the Claude Vision flow is unaffected.
const ALLOWED_EXTS = new Set(["pdf", "csv", "txt", "md"])
const MAX_BYTES = 10 * 1024 * 1024 // 10 MB

// Resolve storage root relative to process.cwd() which is always apps/web/ root.
// In Next.js, __dirname in production points to .next/server/, not source tree.
const STORAGE_ROOT = path.resolve(
  process.cwd(),
  "../../apps/python/input/attachments"
)

export async function POST(req: Request) {
  // Reject oversized requests before buffering the body.
  const contentLength = Number(req.headers.get("content-length") ?? 0)
  if (contentLength > MAX_BYTES) {
    return NextResponse.json({ error: "File must be under 10 MB" }, { status: 400 })
  }

  const formData = await req.formData()
  const file = formData.get("file")

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file provided" }, { status: 400 })
  }

  const ext = file.name.split(".").pop()?.toLowerCase() ?? ""
  if (!ALLOWED_EXTS.has(ext)) {
    return NextResponse.json(
      { error: `File type ".${ext}" is not allowed. Allowed: pdf, csv, txt, md` },
      { status: 400 }
    )
  }

  const bytes = await file.arrayBuffer()
  if (bytes.byteLength > MAX_BYTES) {
    return NextResponse.json({ error: "File must be under 10 MB" }, { status: 400 })
  }

  const today = new Date().toISOString().slice(0, 10) // YYYY-MM-DD
  const filename = `${randomUUID()}.${ext}`
  const dir = path.join(STORAGE_ROOT, today)
  const filepath = path.join(dir, filename)

  await mkdir(dir, { recursive: true })
  await writeFile(filepath, Buffer.from(bytes))

  const url = `/api/attachments/${today}/${filename}`
  // `name` is the original filename so the UI can render [name](url).
  return NextResponse.json({ url, path: filepath, name: file.name })
}
