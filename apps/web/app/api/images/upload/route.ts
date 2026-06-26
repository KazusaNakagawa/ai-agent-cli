// apps/web/app/api/images/upload/route.ts
import { randomUUID } from "crypto"
import { mkdir, writeFile } from "fs/promises"
import { NextResponse } from "next/server"
import path from "path"

const ALLOWED_EXTS = new Set(["jpg", "jpeg", "png", "gif", "webp"])
const MAX_BYTES = 5 * 1024 * 1024 // 5 MB

// Resolve storage root relative to this file's location:
// apps/web/app/api/images/upload/ → ../../../../.. → repo root → apps/python/input/images
const STORAGE_ROOT = path.resolve(
  __dirname,
  "../../../../../apps/python/input/images"
)

export async function POST(req: Request) {
  const formData = await req.formData()
  const file = formData.get("file")

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file provided" }, { status: 400 })
  }

  const ext = file.name.split(".").pop()?.toLowerCase() ?? ""
  if (!ALLOWED_EXTS.has(ext)) {
    return NextResponse.json(
      { error: `File type ".${ext}" is not allowed. Allowed: jpg, jpeg, png, gif, webp` },
      { status: 400 }
    )
  }

  const bytes = await file.arrayBuffer()
  if (bytes.byteLength > MAX_BYTES) {
    return NextResponse.json(
      { error: "Image must be under 5 MB" },
      { status: 400 }
    )
  }

  const today = new Date().toISOString().slice(0, 10) // YYYY-MM-DD
  const filename = `${randomUUID()}.${ext}`
  const dir = path.join(STORAGE_ROOT, today)
  const filepath = path.join(dir, filename)

  await mkdir(dir, { recursive: true })
  await writeFile(filepath, Buffer.from(bytes))

  const url = `/api/images/${today}/${filename}`
  return NextResponse.json({ url })
}
