# Image Insert Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add image insertion (via "+" button and drag-and-drop) to QA chat and Journal text areas, storing images locally under `apps/python/input/images/YYYY-MM-DD/` and inserting `![image](url)` at cursor.

**Architecture:** A shared `ImageInsertButton` component and `useImageDrop` hook both call a `uploadImage()` utility that POSTs to `/api/images/upload`. That Next.js Route Handler writes the file to `apps/python/input/images/YYYY-MM-DD/<uuid>.<ext>` and returns a URL served by `/api/images/[...path]`. The catch-all proxy at `app/api/[...path]` is NOT used for these routes — the new dedicated routes match first in the App Router.

**Tech Stack:** Next.js 14 App Router, TypeScript, Vitest + @testing-library/react, Node.js `fs/promises`, `uuid`

## Global Constraints

- Test runner: `vitest run` from `apps/web/`
- Test files: `apps/web/tests/**/*.test.{ts,tsx}`
- Path alias `@/` maps to `apps/web/`
- Allowed image types: `jpg`, `jpeg`, `png`, `gif`, `webp`
- Max file size: 5 MB
- Storage root: `apps/python/input/images/` (relative to repo root, i.e. `../../apps/python/input/images` from `apps/web/`)
- URL pattern returned by upload: `/api/images/YYYY-MM-DD/<uuid>.<ext>`
- Markdown snippet format: `![image](/api/images/YYYY-MM-DD/<uuid>.<ext>)`
- No placeholder text anywhere in code

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `apps/web/lib/imageUpload.ts` | `uploadImage(file)` → Markdown snippet |
| Create | `apps/web/lib/insertAtCursor.ts` | Insert text at textarea cursor position |
| Create | `apps/web/components/ui/ImageInsertButton.tsx` | "+" button → file picker → upload → onInsert |
| Create | `apps/web/lib/hooks/useImageDrop.ts` | Drag-and-drop onto textarea ref → upload → onInsert |
| Create | `apps/web/app/api/images/upload/route.ts` | POST handler: validate, save, return URL |
| Create | `apps/web/app/api/images/[...path]/route.ts` | GET handler: serve saved image files |
| Create | `apps/web/tests/imageUpload.test.ts` | Unit tests for `uploadImage` |
| Create | `apps/web/tests/insertAtCursor.test.ts` | Unit tests for `insertAtCursor` |
| Create | `apps/web/tests/ImageInsertButton.test.tsx` | Component tests |
| Create | `apps/web/tests/useImageDrop.test.tsx` | Hook tests |
| Modify | `apps/web/components/chat/ChatComposer.tsx` | Add `ImageInsertButton` + `useImageDrop` |
| Modify | `apps/web/components/screens/JournalScreen.tsx` | Add to "Record today" and Brainstorm textareas |

---

## Task 1: `insertAtCursor` utility

**Files:**
- Create: `apps/web/lib/insertAtCursor.ts`
- Create: `apps/web/tests/insertAtCursor.test.ts`

**Interfaces:**
- Produces:
  ```ts
  function insertAtCursor(
    ref: React.RefObject<HTMLTextAreaElement>,
    setValue: (v: string) => void,
    snippet: string
  ): void
  ```

- [ ] **Step 1: Write the failing test**

```ts
// apps/web/tests/insertAtCursor.test.ts
import { createRef } from "react"
import { describe, expect, it, vi } from "vitest"
import { insertAtCursor } from "@/lib/insertAtCursor"

describe("insertAtCursor", () => {
  it("inserts snippet at cursor position", () => {
    const el = document.createElement("textarea")
    el.value = "hello world"
    el.selectionStart = 5
    el.selectionEnd = 5
    const ref = { current: el } as React.RefObject<HTMLTextAreaElement>
    const setValue = vi.fn()

    insertAtCursor(ref, setValue, "![image](url)")

    expect(setValue).toHaveBeenCalledWith("hello![image](url) world")
  })

  it("replaces selected text with snippet", () => {
    const el = document.createElement("textarea")
    el.value = "hello world"
    el.selectionStart = 6
    el.selectionEnd = 11
    const ref = { current: el } as React.RefObject<HTMLTextAreaElement>
    const setValue = vi.fn()

    insertAtCursor(ref, setValue, "![image](url)")

    expect(setValue).toHaveBeenCalledWith("hello ![image](url)")
  })

  it("does nothing if ref.current is null", () => {
    const ref = { current: null } as React.RefObject<HTMLTextAreaElement>
    const setValue = vi.fn()
    expect(() => insertAtCursor(ref, setValue, "x")).not.toThrow()
    expect(setValue).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/web && npx vitest run tests/insertAtCursor.test.ts
```

Expected: FAIL — "Cannot find module '@/lib/insertAtCursor'"

- [ ] **Step 3: Implement `insertAtCursor`**

```ts
// apps/web/lib/insertAtCursor.ts
import type { RefObject } from "react"

export function insertAtCursor(
  ref: RefObject<HTMLTextAreaElement>,
  setValue: (v: string) => void,
  snippet: string
): void {
  const el = ref.current
  if (!el) return
  const start = el.selectionStart ?? el.value.length
  const end = el.selectionEnd ?? el.value.length
  const next = el.value.slice(0, start) + snippet + el.value.slice(end)
  setValue(next)
  // Restore focus and move caret after snippet
  requestAnimationFrame(() => {
    el.focus()
    el.selectionStart = start + snippet.length
    el.selectionEnd = start + snippet.length
  })
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd apps/web && npx vitest run tests/insertAtCursor.test.ts
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/insertAtCursor.ts apps/web/tests/insertAtCursor.test.ts
git commit -m "feat(web): add insertAtCursor utility"
```

---

## Task 2: Upload API route (`POST /api/images/upload`)

**Files:**
- Create: `apps/web/app/api/images/upload/route.ts`

**Interfaces:**
- Produces: `POST /api/images/upload` accepts `multipart/form-data` with field `file`, returns `{ url: string }` or `{ error: string }`

Note: This route runs in Node.js (Next.js Route Handler). No unit test for this route — it writes to the filesystem; integration-test manually in Task 6.

- [ ] **Step 1: Install `uuid` if not already present**

```bash
cd apps/web && npm list uuid 2>/dev/null || npm install uuid && npm install --save-dev @types/uuid
```

- [ ] **Step 2: Create the upload route**

```ts
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
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/api/images/upload/route.ts
git commit -m "feat(web): add POST /api/images/upload route"
```

---

## Task 3: Image serve route (`GET /api/images/[...path]`)

**Files:**
- Create: `apps/web/app/api/images/[...path]/route.ts`

**Interfaces:**
- Produces: `GET /api/images/<YYYY-MM-DD>/<filename>` streams the file with correct `Content-Type`

- [ ] **Step 1: Create the serve route**

```ts
// apps/web/app/api/images/[...path]/route.ts
import { readFile } from "fs/promises"
import { NextResponse } from "next/server"
import path from "path"

const STORAGE_ROOT = path.resolve(
  __dirname,
  "../../../../../../apps/python/input/images"
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
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/app/api/images/\[...path\]/route.ts
git commit -m "feat(web): add GET /api/images/[...path] serve route"
```

---

## Task 4: `uploadImage` client utility

**Files:**
- Create: `apps/web/lib/imageUpload.ts`
- Create: `apps/web/tests/imageUpload.test.ts`

**Interfaces:**
- Consumes: `POST /api/images/upload` (Task 2)
- Consumes: `insertAtCursor` from `@/lib/insertAtCursor` (Task 1)
- Produces:
  ```ts
  export async function uploadImage(file: File): Promise<string>
  // Returns Markdown snippet e.g. "![image](/api/images/2026-06-26/uuid.png)"
  // Throws Error with human-readable message on failure
  ```

- [ ] **Step 1: Write failing tests**

```ts
// apps/web/tests/imageUpload.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { uploadImage } from "@/lib/imageUpload"

function makeFile(name: string, type: string, size = 100): File {
  const buf = new Uint8Array(size)
  return new File([buf], name, { type })
}

describe("uploadImage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("returns markdown snippet on success", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ url: "/api/images/2026-06-26/abc.png" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )
    const file = makeFile("photo.png", "image/png")
    const result = await uploadImage(file)
    expect(result).toBe("![image](/api/images/2026-06-26/abc.png)")
  })

  it("throws with server error message on 400", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: "Image must be under 5 MB" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      })
    )
    const file = makeFile("big.png", "image/png")
    await expect(uploadImage(file)).rejects.toThrow("Image must be under 5 MB")
  })

  it("throws on network failure", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("Network error"))
    const file = makeFile("photo.png", "image/png")
    await expect(uploadImage(file)).rejects.toThrow("Network error")
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/web && npx vitest run tests/imageUpload.test.ts
```

Expected: FAIL — "Cannot find module '@/lib/imageUpload'"

- [ ] **Step 3: Implement `uploadImage`**

```ts
// apps/web/lib/imageUpload.ts
export async function uploadImage(file: File): Promise<string> {
  const body = new FormData()
  body.append("file", file)

  const res = await fetch("/api/images/upload", { method: "POST", body })
  const json = (await res.json()) as { url?: string; error?: string }

  if (!res.ok || !json.url) {
    throw new Error(json.error ?? "Upload failed, please try again")
  }

  return `![image](${json.url})`
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd apps/web && npx vitest run tests/imageUpload.test.ts
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/imageUpload.ts apps/web/tests/imageUpload.test.ts
git commit -m "feat(web): add uploadImage client utility"
```

---

## Task 5: `ImageInsertButton` component

**Files:**
- Create: `apps/web/components/ui/ImageInsertButton.tsx`
- Create: `apps/web/tests/ImageInsertButton.test.tsx`

**Interfaces:**
- Consumes: `uploadImage` from `@/lib/imageUpload` (Task 4)
- Produces:
  ```ts
  type ImageInsertButtonProps = {
    onInsert: (snippet: string) => void
    disabled?: boolean
  }
  export function ImageInsertButton(props: ImageInsertButtonProps): JSX.Element
  ```

- [ ] **Step 1: Write failing tests**

```tsx
// apps/web/tests/ImageInsertButton.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ImageInsertButton } from "@/components/ui/ImageInsertButton"

vi.mock("@/lib/imageUpload", () => ({
  uploadImage: vi.fn(),
}))

import { uploadImage } from "@/lib/imageUpload"

describe("ImageInsertButton", () => {
  afterEach(() => vi.clearAllMocks())

  it("renders a + button", () => {
    render(<ImageInsertButton onInsert={vi.fn()} />)
    expect(screen.getByRole("button", { name: /insert image/i })).toBeInTheDocument()
  })

  it("calls onInsert with snippet after successful upload", async () => {
    vi.mocked(uploadImage).mockResolvedValue("![image](/api/images/2026-06-26/x.png)")
    const onInsert = vi.fn()
    render(<ImageInsertButton onInsert={onInsert} />)

    const input = document.querySelector("input[type=file]") as HTMLInputElement
    const file = new File(["x"], "photo.png", { type: "image/png" })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => expect(onInsert).toHaveBeenCalledWith("![image](/api/images/2026-06-26/x.png)"))
  })

  it("shows error message when upload fails", async () => {
    vi.mocked(uploadImage).mockRejectedValue(new Error("Image must be under 5 MB"))
    render(<ImageInsertButton onInsert={vi.fn()} />)

    const input = document.querySelector("input[type=file]") as HTMLInputElement
    const file = new File(["x"], "big.png", { type: "image/png" })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() =>
      expect(screen.getByText("Image must be under 5 MB")).toBeInTheDocument()
    )
  })

  it("is disabled when disabled prop is true", () => {
    render(<ImageInsertButton onInsert={vi.fn()} disabled />)
    expect(screen.getByRole("button", { name: /insert image/i })).toBeDisabled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/web && npx vitest run tests/ImageInsertButton.test.tsx
```

Expected: FAIL — "Cannot find module '@/components/ui/ImageInsertButton'"

- [ ] **Step 3: Implement `ImageInsertButton`**

```tsx
// apps/web/components/ui/ImageInsertButton.tsx
"use client"
import { useRef, useState } from "react"
import { uploadImage } from "@/lib/imageUpload"

type Props = {
  onInsert: (snippet: string) => void
  disabled?: boolean
}

export function ImageInsertButton({ onInsert, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setError(null)
    setUploading(true)
    try {
      const snippet = await uploadImage(file)
      onInsert(snippet)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed, please try again")
    } finally {
      setUploading(false)
      // Reset so the same file can be re-selected
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        className="hidden"
        onChange={handleChange}
      />
      <button
        type="button"
        aria-label="Insert image"
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
        className="flex h-8 w-8 items-center justify-center rounded-md border bg-background text-sm font-medium hover:bg-accent disabled:opacity-50"
      >
        {uploading ? "…" : "+"}
      </button>
      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd apps/web && npx vitest run tests/ImageInsertButton.test.tsx
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ui/ImageInsertButton.tsx apps/web/tests/ImageInsertButton.test.tsx
git commit -m "feat(web): add ImageInsertButton component"
```

---

## Task 6: `useImageDrop` hook

**Files:**
- Create: `apps/web/lib/hooks/useImageDrop.ts`
- Create: `apps/web/tests/useImageDrop.test.tsx`

**Interfaces:**
- Consumes: `uploadImage` from `@/lib/imageUpload` (Task 4)
- Produces:
  ```ts
  function useImageDrop(
    ref: React.RefObject<HTMLTextAreaElement>,
    onInsert: (snippet: string) => void
  ): { isDragging: boolean }
  ```

- [ ] **Step 1: Write failing tests**

```tsx
// apps/web/tests/useImageDrop.test.tsx
import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useImageDrop } from "@/lib/hooks/useImageDrop"

vi.mock("@/lib/imageUpload", () => ({
  uploadImage: vi.fn(),
}))

import { uploadImage } from "@/lib/imageUpload"

function makeTextarea() {
  const el = document.createElement("textarea")
  document.body.appendChild(el)
  return el
}

describe("useImageDrop", () => {
  let el: HTMLTextAreaElement

  beforeEach(() => {
    el = makeTextarea()
  })

  afterEach(() => {
    el.remove()
    vi.clearAllMocks()
  })

  it("isDragging is false initially", () => {
    const ref = { current: el }
    const { result } = renderHook(() => useImageDrop(ref, vi.fn()))
    expect(result.current.isDragging).toBe(false)
  })

  it("sets isDragging true on dragover with image file", () => {
    const ref = { current: el }
    const { result } = renderHook(() => useImageDrop(ref, vi.fn()))

    act(() => {
      el.dispatchEvent(
        new DragEvent("dragover", {
          bubbles: true,
          dataTransfer: Object.assign(new DataTransfer(), {
            types: ["Files"],
          }),
        })
      )
    })

    expect(result.current.isDragging).toBe(true)
  })

  it("calls onInsert with snippet on drop", async () => {
    vi.mocked(uploadImage).mockResolvedValue("![image](/api/images/2026-06-26/x.png)")
    const onInsert = vi.fn()
    const ref = { current: el }
    renderHook(() => useImageDrop(ref, onInsert))

    const file = new File(["x"], "photo.png", { type: "image/png" })
    const dt = new DataTransfer()
    dt.items.add(file)

    await act(async () => {
      el.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer: dt }))
      await Promise.resolve()
    })

    expect(onInsert).toHaveBeenCalledWith("![image](/api/images/2026-06-26/x.png)")
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/web && npx vitest run tests/useImageDrop.test.tsx
```

Expected: FAIL — "Cannot find module '@/lib/hooks/useImageDrop'"

- [ ] **Step 3: Implement `useImageDrop`**

```ts
// apps/web/lib/hooks/useImageDrop.ts
"use client"
import { useEffect, useRef, useState } from "react"
import type { RefObject } from "react"
import { uploadImage } from "@/lib/imageUpload"

export function useImageDrop(
  ref: RefObject<HTMLTextAreaElement>,
  onInsert: (snippet: string) => void
): { isDragging: boolean } {
  const [isDragging, setIsDragging] = useState(false)
  const onInsertRef = useRef(onInsert)
  onInsertRef.current = onInsert

  useEffect(() => {
    const el = ref.current
    if (!el) return

    function onDragOver(e: DragEvent) {
      if (!e.dataTransfer?.types.includes("Files")) return
      e.preventDefault()
      setIsDragging(true)
    }

    function onDragLeave() {
      setIsDragging(false)
    }

    async function onDrop(e: DragEvent) {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer?.files[0]
      if (!file || !file.type.startsWith("image/")) return
      try {
        const snippet = await uploadImage(file)
        onInsertRef.current(snippet)
      } catch {
        // Silent drop failure — no UI anchor to show error on
      }
    }

    el.addEventListener("dragover", onDragOver)
    el.addEventListener("dragleave", onDragLeave)
    el.addEventListener("drop", onDrop)
    return () => {
      el.removeEventListener("dragover", onDragOver)
      el.removeEventListener("dragleave", onDragLeave)
      el.removeEventListener("drop", onDrop)
    }
  }, [ref])

  return { isDragging }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd apps/web && npx vitest run tests/useImageDrop.test.tsx
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/hooks/useImageDrop.ts apps/web/tests/useImageDrop.test.tsx
git commit -m "feat(web): add useImageDrop hook"
```

---

## Task 7: Integrate into `ChatComposer`

**Files:**
- Modify: `apps/web/components/chat/ChatComposer.tsx`

**Interfaces:**
- Consumes: `ImageInsertButton` from `@/components/ui/ImageInsertButton` (Task 5)
- Consumes: `useImageDrop` from `@/lib/hooks/useImageDrop` (Task 6)
- Consumes: `insertAtCursor` from `@/lib/insertAtCursor` (Task 1)
- The existing `Props` type gains `textareaRef?: RefObject<HTMLTextAreaElement>` — but to keep the caller unchanged, we create the ref internally instead.

- [ ] **Step 1: Modify `ChatComposer.tsx`**

Replace the file content with:

```tsx
"use client"
import { useRef, type KeyboardEvent } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ImageInsertButton } from "@/components/ui/ImageInsertButton"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import { insertAtCursor } from "@/lib/insertAtCursor"

type Props = {
  input: string
  setInput: (value: string) => void
  busy: boolean
  supportsMic: boolean
  listening: boolean
  onToggleMic: (prefix: string) => void
  onSend: () => void
  onCancel: () => void
  onHistoryKeyDown?: (e: KeyboardEvent<HTMLTextAreaElement>) => void
}

export function ChatComposer({
  input,
  setInput,
  busy,
  supportsMic,
  listening,
  onToggleMic,
  onSend,
  onCancel,
  onHistoryKeyDown,
}: Props) {
  const composingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { isDragging } = useImageDrop(textareaRef, (snippet) =>
    insertAtCursor(textareaRef, setInput, snippet)
  )

  return (
    <Card>
      <CardContent className="space-y-2 pt-6">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            aria-label="Chat message"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onCompositionStart={() => {
              composingRef.current = true
            }}
            onCompositionEnd={() => {
              composingRef.current = false
            }}
            onKeyDown={(e) => {
              if (composingRef.current || e.nativeEvent.isComposing) return
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                onSend()
                return
              }
              onHistoryKeyDown?.(e)
            }}
            placeholder="Ask about today's briefing…"
            rows={2}
            className={`flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm${isDragging ? " ring-2 ring-primary" : ""}`}
            data-testid="chat-input"
          />
          {supportsMic && (
            <Button
              type="button"
              variant={listening ? "destructive" : "outline"}
              onClick={() => onToggleMic(input)}
              data-testid="mic-button"
              aria-label={listening ? "音声入力停止" : "音声入力開始"}
              aria-pressed={listening}
              title={listening ? "音声入力停止" : "音声入力開始 (ja-JP)"}
            >
              {listening ? "🛑" : "🎤"}
            </Button>
          )}
          {busy ? (
            <Button
              type="button"
              variant="destructive"
              onClick={onCancel}
              data-testid="cancel-button"
              title="送信中の応答を中止 (Esc)"
            >
              Cancel
            </Button>
          ) : (
            <Button
              onClick={onSend}
              disabled={input.trim().length === 0}
              data-testid="send-button"
            >
              Send
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ImageInsertButton
            onInsert={(snippet) => insertAtCursor(textareaRef, setInput, snippet)}
            disabled={busy}
          />
        </div>
        {!supportsMic && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="mic-unsupported"
          >
            Voice input is unavailable in this browser (Chrome / Edge supported).
          </p>
        )}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Run all tests**

```bash
cd apps/web && npx vitest run
```

Expected: all existing tests PASS (ChatComposer renders with the new button)

- [ ] **Step 3: Commit**

```bash
git add apps/web/components/chat/ChatComposer.tsx
git commit -m "feat(web): integrate ImageInsertButton and useImageDrop into ChatComposer"
```

---

## Task 8: Integrate into `JournalScreen`

**Files:**
- Modify: `apps/web/components/screens/JournalScreen.tsx`

**Interfaces:**
- Consumes: `ImageInsertButton` from `@/components/ui/ImageInsertButton` (Task 5)
- Consumes: `useImageDrop` from `@/lib/hooks/useImageDrop` (Task 6)
- Consumes: `insertAtCursor` from `@/lib/insertAtCursor` (Task 1)

There are two textareas: `composeRef` ("Record today") and a new `brainstormRef` (Brainstorm question).

- [ ] **Step 1: Add imports and refs to `JournalScreen.tsx`**

At the top of the file, add the three imports after the existing imports:

```ts
import { ImageInsertButton } from "@/components/ui/ImageInsertButton"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import { insertAtCursor } from "@/lib/insertAtCursor"
```

- [ ] **Step 2: Add `brainstormRef` and drop hooks**

Locate the line `const composeRef = useRef<HTMLTextAreaElement>(null)` (around line 63) and add after it:

```ts
const brainstormRef = useRef<HTMLTextAreaElement>(null)
const { isDragging: isComposeDragging } = useImageDrop(composeRef, (snippet) =>
  insertAtCursor(composeRef, setEntry, snippet)
)
const { isDragging: isBrainstormDragging } = useImageDrop(brainstormRef, (snippet) =>
  insertAtCursor(brainstormRef, setQuestion, snippet)
)
```

- [ ] **Step 3: Update "Record today" textarea**

Find the `<textarea ref={composeRef}` block (around line 506) and:
1. Add `className` drag ring: append `${isComposeDragging ? " ring-2 ring-primary" : ""}` to the existing className string
2. After the `</textarea>`, add `ImageInsertButton` before the existing Save button div:

```tsx
<div className="flex items-center gap-2">
  <ImageInsertButton
    onInsert={(snippet) => insertAtCursor(composeRef, setEntry, snippet)}
    disabled={saving}
  />
</div>
```

- [ ] **Step 4: Update Brainstorm textarea**

Find the second `<textarea` (around line 558, the Brainstorm question textarea) and:
1. Add `ref={brainstormRef}` to it
2. Append `${isBrainstormDragging ? " ring-2 ring-primary" : ""}` to its className
3. After `</textarea>`, add:

```tsx
<div className="flex items-center gap-2">
  <ImageInsertButton
    onInsert={(snippet) => insertAtCursor(brainstormRef, setQuestion, snippet)}
  />
</div>
```

- [ ] **Step 5: Run all tests**

```bash
cd apps/web && npx vitest run
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/screens/JournalScreen.tsx
git commit -m "feat(web): integrate ImageInsertButton and useImageDrop into JournalScreen"
```

---

## Task 9: Manual integration test + PR

- [ ] **Step 1: Start the dev server**

```bash
cd apps/web && npm run dev
```

Open `http://localhost:3001`

- [ ] **Step 2: Test QA chat image insert**

1. Navigate to the QA/Chat page
2. Click the "+" button below the chat textarea
3. Select a PNG or JPEG image (under 5 MB)
4. Verify `![image](/api/images/YYYY-MM-DD/<uuid>.png)` appears in the textarea at cursor position
5. Verify the file exists at `apps/python/input/images/YYYY-MM-DD/<uuid>.png`

- [ ] **Step 3: Test drag-and-drop in chat**

1. Drag an image file onto the chat textarea
2. Verify the border highlights (ring-2 ring-primary) while dragging
3. Verify the snippet is inserted on drop

- [ ] **Step 4: Test Journal "Record today"**

1. Navigate to Journal
2. Click "+" below "Record today" textarea; pick an image
3. Verify snippet inserted

- [ ] **Step 5: Test Journal Brainstorm**

1. Click "+" below the Brainstorm textarea; pick an image
2. Verify snippet inserted

- [ ] **Step 6: Test error cases**

1. Try uploading a `.pdf` file — verify error "File type ".pdf" is not allowed"
2. Try uploading an image > 5 MB — verify error "Image must be under 5 MB"

- [ ] **Step 7: Push and create PR**

```bash
git push -u origin feat/issue-308-image-insert-component
gh pr create \
  --title "feat(web): add shared image insert component with + button and drag-and-drop" \
  --body "$(cat <<'EOF'
## Summary

- Add `ImageInsertButton` (`+` button) and `useImageDrop` hook as shared components
- Add `POST /api/images/upload` and `GET /api/images/[...path]` Next.js Route Handlers
- Images stored at `apps/python/input/images/YYYY-MM-DD/<uuid>.<ext>`
- Integrated into ChatComposer and JournalScreen (Record today + Brainstorm)

## Test plan

- [ ] `npx vitest run` passes in `apps/web/`
- [ ] QA chat: "+" button inserts image snippet at cursor
- [ ] QA chat: drag-and-drop inserts image snippet
- [ ] Journal "Record today": same
- [ ] Journal Brainstorm: same
- [ ] Non-image file shows error
- [ ] File > 5 MB shows error

Closes #308
EOF
)"
```
