# Image Vision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to attach images to QA chat and Journal Brainstorm prompts so Claude can actually see and discuss them, using the existing OAuth `claude` CLI with base64 stdin JSON.

**Architecture:** Images are uploaded to `apps/python/input/images/YYYY-MM-DD/<uuid>.<ext>` and the server returns both a preview URL and an absolute path. On send, the path is forwarded to the Python backend which base64-encodes the file and pipes a multimodal JSON message to `claude -p -`. Shared React components (`ImageAttachArea`) and a shared hook (`useImageDrop`) are used in both ChatComposer and JournalScreen to avoid duplication.

**Tech Stack:** Next.js 14 App Router, TypeScript, React, Vitest + @testing-library/react (frontend); Python 3.11+, FastAPI, pytest, unittest.mock (backend)

## Global Constraints

- Branch: `feat/issue-308-image-insert-component`
- Frontend test runner: `cd apps/web && npx vitest run` — all tests must stay green
- Backend test runner: `cd apps/python && .venv/bin/pytest -v` — all tests must stay green
- Path alias `@/` maps to `apps/web/`
- Frontend test files: `apps/web/tests/**/*.test.{ts,tsx}`
- Backend test files: `apps/python/tests/`
- Storage root: `apps/python/input/images/` (resolved via `process.cwd()` in Next.js, `Path(__file__).resolve().parents[N]` in Python)
- Allowed image extensions: `jpg`, `jpeg`, `png`, `gif`, `webp`
- Max file size: 5 MB
- Markdown snippet insertion is NOT used — images are attached as `ImageAttachment` state
- Code comments in English
- Conventional commits format

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `apps/web/lib/types/image.ts` | Shared `ImageAttachment` type |
| Modify | `apps/web/lib/imageUpload.ts` | Return `ImageAttachment` instead of Markdown snippet |
| Modify | `apps/web/app/api/images/upload/route.ts` | Also return `path` in response |
| Modify | `apps/web/components/ui/ImageInsertButton.tsx` | Change `onInsert(snippet)` → `onAttach(ImageAttachment)` |
| Modify | `apps/web/lib/hooks/useImageDrop.ts` | Fix D&D bug + change to `onAttach(ImageAttachment)` |
| Create | `apps/web/components/ui/ImageAttachmentPreview.tsx` | Shared thumbnail + ✕ remove button |
| Create | `apps/web/components/ui/ImageAttachArea.tsx` | Shared wrapper: button + preview + drop zone |
| Modify | `apps/web/components/chat/ChatComposer.tsx` | Use `ImageAttachArea`; send `image_path` |
| Modify | `apps/web/components/screens/JournalScreen.tsx` | Same pattern for both textareas |
| Delete | `apps/web/lib/insertAtCursor.ts` | No longer needed (no Markdown insertion) |
| Delete | `apps/web/tests/insertAtCursor.test.ts` | Corresponding test |
| Modify | `apps/python/src/claude_runner.py` | Add `run_claude_with_image()` |
| Modify | `apps/python/web/routers/chat.py` | Add `image_path` to bodies; route to vision |
| Modify | `apps/python/tests/test_api_chat.py` | Tests for vision path |

---

## Task 1: Shared `ImageAttachment` type + update `imageUpload.ts` + update upload route

**Files:**
- Create: `apps/web/lib/types/image.ts`
- Modify: `apps/web/lib/imageUpload.ts`
- Modify: `apps/web/app/api/images/upload/route.ts`
- Modify: `apps/web/tests/imageUpload.test.ts`

**Interfaces:**
- Produces:
  ```ts
  // apps/web/lib/types/image.ts
  export type ImageAttachment = { url: string; path: string }

  // apps/web/lib/imageUpload.ts
  export async function uploadImage(file: File): Promise<ImageAttachment>
  // Returns { url: "/api/images/YYYY-MM-DD/uuid.ext", path: "/abs/path/..." }
  // Throws Error with human-readable message on failure
  ```

- [ ] **Step 1: Write failing tests**

```ts
// apps/web/tests/imageUpload.test.ts  (replace entire file)
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ImageAttachment } from "@/lib/types/image"
import { uploadImage } from "@/lib/imageUpload"

function makeFile(name: string, type: string, size = 100): File {
  const buf = new Uint8Array(size)
  return new File([buf], name, { type })
}

describe("uploadImage", () => {
  beforeEach(() => { vi.stubGlobal("fetch", vi.fn()) })
  afterEach(() => { vi.restoreAllMocks() })

  it("returns ImageAttachment on success", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          url: "/api/images/2026-06-26/abc.png",
          path: "/abs/apps/python/input/images/2026-06-26/abc.png",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    )
    const file = makeFile("photo.png", "image/png")
    const result: ImageAttachment = await uploadImage(file)
    expect(result.url).toBe("/api/images/2026-06-26/abc.png")
    expect(result.path).toBe("/abs/apps/python/input/images/2026-06-26/abc.png")
  })

  it("throws with server error message on 400", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: "Image must be under 5 MB" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      })
    )
    await expect(uploadImage(makeFile("big.png", "image/png"))).rejects.toThrow(
      "Image must be under 5 MB"
    )
  })

  it("throws on network failure", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("Network error"))
    await expect(uploadImage(makeFile("photo.png", "image/png"))).rejects.toThrow(
      "Network error"
    )
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/web && npx vitest run tests/imageUpload.test.ts
```

Expected: FAIL — type errors or assertion failures

- [ ] **Step 3: Create shared type**

```ts
// apps/web/lib/types/image.ts
export type ImageAttachment = { url: string; path: string }
```

- [ ] **Step 4: Update `imageUpload.ts`**

```ts
// apps/web/lib/imageUpload.ts
import type { ImageAttachment } from "@/lib/types/image"

export async function uploadImage(file: File): Promise<ImageAttachment> {
  const body = new FormData()
  body.append("file", file)

  const res = await fetch("/api/images/upload", { method: "POST", body })
  const json = (await res.json()) as { url?: string; path?: string; error?: string }

  if (!res.ok || !json.url || !json.path) {
    throw new Error(json.error ?? "Upload failed, please try again")
  }

  return { url: json.url, path: json.path }
}
```

- [ ] **Step 5: Update upload route to return `path`**

In `apps/web/app/api/images/upload/route.ts`, find the final `return NextResponse.json({ url })` line and replace with:

```ts
  return NextResponse.json({ url, path: filepath })
```

- [ ] **Step 6: Run tests**

```bash
cd apps/web && npx vitest run tests/imageUpload.test.ts
```

Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add apps/web/lib/types/image.ts apps/web/lib/imageUpload.ts \
        apps/web/app/api/images/upload/route.ts apps/web/tests/imageUpload.test.ts
git commit -m "feat(web): add ImageAttachment type; uploadImage returns {url,path}"
```

---

## Task 2: Update `ImageInsertButton` — `onInsert` → `onAttach`

**Files:**
- Modify: `apps/web/components/ui/ImageInsertButton.tsx`
- Modify: `apps/web/tests/ImageInsertButton.test.tsx`

**Interfaces:**
- Consumes: `ImageAttachment` from `@/lib/types/image` (Task 1)
- Consumes: `uploadImage` returning `ImageAttachment` (Task 1)
- Produces:
  ```ts
  type ImageInsertButtonProps = {
    onAttach: (image: ImageAttachment) => void
    disabled?: boolean
  }
  export function ImageInsertButton(props: ImageInsertButtonProps): JSX.Element
  ```

- [ ] **Step 1: Rewrite test file**

```tsx
// apps/web/tests/ImageInsertButton.test.tsx  (replace entire file)
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ImageAttachment } from "@/lib/types/image"
import { ImageInsertButton } from "@/components/ui/ImageInsertButton"

vi.mock("@/lib/imageUpload", () => ({ uploadImage: vi.fn() }))
import { uploadImage } from "@/lib/imageUpload"

const ATTACHMENT: ImageAttachment = {
  url: "/api/images/2026-06-26/x.png",
  path: "/abs/input/images/2026-06-26/x.png",
}

describe("ImageInsertButton", () => {
  afterEach(() => vi.clearAllMocks())

  it("renders a + button", () => {
    render(<ImageInsertButton onAttach={vi.fn()} />)
    expect(screen.getByRole("button", { name: /attach image/i })).toBeInTheDocument()
  })

  it("calls onAttach with ImageAttachment after successful upload", async () => {
    vi.mocked(uploadImage).mockResolvedValue(ATTACHMENT)
    const onAttach = vi.fn()
    render(<ImageInsertButton onAttach={onAttach} />)

    const input = document.querySelector("input[type=file]") as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(["x"], "photo.png", { type: "image/png" })] } })

    await waitFor(() => expect(onAttach).toHaveBeenCalledWith(ATTACHMENT))
  })

  it("shows error message when upload fails", async () => {
    vi.mocked(uploadImage).mockRejectedValue(new Error("Image must be under 5 MB"))
    render(<ImageInsertButton onAttach={vi.fn()} />)

    const input = document.querySelector("input[type=file]") as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(["x"], "big.png", { type: "image/png" })] } })

    await waitFor(() =>
      expect(screen.getByText("Image must be under 5 MB")).toBeInTheDocument()
    )
  })

  it("is disabled when disabled prop is true", () => {
    render(<ImageInsertButton onAttach={vi.fn()} disabled />)
    expect(screen.getByRole("button", { name: /attach image/i })).toBeDisabled()
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/web && npx vitest run tests/ImageInsertButton.test.tsx
```

Expected: FAIL — type errors (`onInsert` vs `onAttach`)

- [ ] **Step 3: Rewrite `ImageInsertButton.tsx`**

```tsx
// apps/web/components/ui/ImageInsertButton.tsx
"use client"
import { useRef, useState } from "react"
import type { ImageAttachment } from "@/lib/types/image"
import { uploadImage } from "@/lib/imageUpload"

type Props = {
  onAttach: (image: ImageAttachment) => void
  disabled?: boolean
}

export function ImageInsertButton({ onAttach, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setError(null)
    setUploading(true)
    try {
      const attachment = await uploadImage(file)
      onAttach(attachment)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed, please try again")
    } finally {
      setUploading(false)
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
        aria-label="Attach image"
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
        className="flex h-8 w-8 items-center justify-center rounded-md border bg-background text-sm font-medium hover:bg-accent disabled:opacity-50"
      >
        {uploading ? "…" : "+"}
      </button>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
cd apps/web && npx vitest run tests/ImageInsertButton.test.tsx
```

Expected: 4 tests PASS

- [ ] **Step 5: Run full suite to check for regressions**

```bash
cd apps/web && npx vitest run
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/ui/ImageInsertButton.tsx apps/web/tests/ImageInsertButton.test.tsx
git commit -m "feat(web): change ImageInsertButton to onAttach(ImageAttachment)"
```

---

## Task 3: Fix `useImageDrop` — D&D bug + `onAttach`

**Files:**
- Modify: `apps/web/lib/hooks/useImageDrop.ts`
- Modify: `apps/web/tests/useImageDrop.test.tsx`

**Interfaces:**
- Consumes: `ImageAttachment` from `@/lib/types/image` (Task 1)
- Consumes: `uploadImage` returning `ImageAttachment` (Task 1)
- Produces:
  ```ts
  function useImageDrop(
    ref: RefObject<HTMLTextAreaElement>,
    onAttach: (image: ImageAttachment) => void
  ): { isDragging: boolean }
  ```

- [ ] **Step 1: Rewrite test file**

```tsx
// apps/web/tests/useImageDrop.test.tsx  (replace entire file)
import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ImageAttachment } from "@/lib/types/image"
import { useImageDrop } from "@/lib/hooks/useImageDrop"

vi.mock("@/lib/imageUpload", () => ({ uploadImage: vi.fn() }))
import { uploadImage } from "@/lib/imageUpload"

const ATTACHMENT: ImageAttachment = {
  url: "/api/images/2026-06-26/x.png",
  path: "/abs/input/2026-06-26/x.png",
}

function makeTextarea() {
  const el = document.createElement("textarea")
  document.body.appendChild(el)
  return el
}

describe("useImageDrop", () => {
  let el: HTMLTextAreaElement
  beforeEach(() => { el = makeTextarea() })
  afterEach(() => { el.remove(); vi.clearAllMocks() })

  it("isDragging is false initially", () => {
    const { result } = renderHook(() => useImageDrop({ current: el }, vi.fn()))
    expect(result.current.isDragging).toBe(false)
  })

  it("sets isDragging true on dragover with Files", () => {
    const { result } = renderHook(() => useImageDrop({ current: el }, vi.fn()))
    act(() => {
      const e = new Event("dragover", { bubbles: true }) as any
      e.dataTransfer = { types: ["Files"] }
      el.dispatchEvent(e)
    })
    expect(result.current.isDragging).toBe(true)
  })

  it("prevents default and stops propagation on dragenter", () => {
    renderHook(() => useImageDrop({ current: el }, vi.fn()))
    const e = new Event("dragenter", { bubbles: true }) as any
    e.preventDefault = vi.fn()
    e.stopPropagation = vi.fn()
    act(() => { el.dispatchEvent(e) })
    expect(e.preventDefault).toHaveBeenCalled()
    expect(e.stopPropagation).toHaveBeenCalled()
  })

  it("calls onAttach with ImageAttachment on drop", async () => {
    vi.mocked(uploadImage).mockResolvedValue(ATTACHMENT)
    const onAttach = vi.fn()
    renderHook(() => useImageDrop({ current: el }, onAttach))

    const file = new File(["x"], "photo.png", { type: "image/png" })
    await act(async () => {
      const e = new Event("drop", { bubbles: true }) as any
      e.preventDefault = vi.fn()
      e.stopPropagation = vi.fn()
      e.dataTransfer = { files: [file] }
      el.dispatchEvent(e)
      await Promise.resolve()
    })

    expect(onAttach).toHaveBeenCalledWith(ATTACHMENT)
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/web && npx vitest run tests/useImageDrop.test.tsx
```

Expected: FAIL — `stopPropagation` test fails, type errors

- [ ] **Step 3: Rewrite `useImageDrop.ts`**

```ts
// apps/web/lib/hooks/useImageDrop.ts
"use client"
import { useEffect, useRef, useState } from "react"
import type { RefObject } from "react"
import type { ImageAttachment } from "@/lib/types/image"
import { uploadImage } from "@/lib/imageUpload"

export function useImageDrop(
  ref: RefObject<HTMLTextAreaElement>,
  onAttach: (image: ImageAttachment) => void
): { isDragging: boolean } {
  const [isDragging, setIsDragging] = useState(false)
  const onAttachRef = useRef(onAttach)
  onAttachRef.current = onAttach

  useEffect(() => {
    const el = ref.current
    if (!el) return

    function onDragEnter(e: DragEvent) {
      e.preventDefault()
      e.stopPropagation()
    }

    function onDragOver(e: DragEvent) {
      if (!e.dataTransfer?.types.includes("Files")) return
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(true)
    }

    function onDragLeave() {
      setIsDragging(false)
    }

    async function onDrop(e: DragEvent) {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)
      const file = e.dataTransfer?.files[0]
      if (!file || !file.type.startsWith("image/")) return
      try {
        const attachment = await uploadImage(file)
        onAttachRef.current(attachment)
      } catch {
        // Silent — no persistent UI anchor for drop errors
      }
    }

    el.addEventListener("dragenter", onDragEnter)
    el.addEventListener("dragover", onDragOver)
    el.addEventListener("dragleave", onDragLeave)
    el.addEventListener("drop", onDrop)
    return () => {
      el.removeEventListener("dragenter", onDragEnter)
      el.removeEventListener("dragover", onDragOver)
      el.removeEventListener("dragleave", onDragLeave)
      el.removeEventListener("drop", onDrop)
    }
  }, [ref])

  return { isDragging }
}
```

- [ ] **Step 4: Run tests**

```bash
cd apps/web && npx vitest run tests/useImageDrop.test.tsx
```

Expected: 4 tests PASS

- [ ] **Step 5: Run full suite**

```bash
cd apps/web && npx vitest run
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/hooks/useImageDrop.ts apps/web/tests/useImageDrop.test.tsx
git commit -m "fix(web): fix D&D dragenter+stopPropagation; useImageDrop uses onAttach"
```

---

## Task 4: `ImageAttachmentPreview` shared component (new)

**Files:**
- Create: `apps/web/components/ui/ImageAttachmentPreview.tsx`
- Create: `apps/web/tests/ImageAttachmentPreview.test.tsx`

**Interfaces:**
- Consumes: `ImageAttachment` from `@/lib/types/image` (Task 1)
- Produces:
  ```ts
  type ImageAttachmentPreviewProps = {
    image: ImageAttachment
    onRemove: () => void
  }
  export function ImageAttachmentPreview(props: ImageAttachmentPreviewProps): JSX.Element
  ```

- [ ] **Step 1: Write failing tests**

```tsx
// apps/web/tests/ImageAttachmentPreview.test.tsx
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { ImageAttachment } from "@/lib/types/image"
import { ImageAttachmentPreview } from "@/components/ui/ImageAttachmentPreview"

const IMAGE: ImageAttachment = {
  url: "/api/images/2026-06-26/abc.png",
  path: "/abs/input/2026-06-26/abc.png",
}

describe("ImageAttachmentPreview", () => {
  it("renders thumbnail with image url as src", () => {
    render(<ImageAttachmentPreview image={IMAGE} onRemove={vi.fn()} />)
    const img = screen.getByRole("img", { name: /attached image/i })
    expect(img).toHaveAttribute("src", IMAGE.url)
  })

  it("calls onRemove when remove button clicked", () => {
    const onRemove = vi.fn()
    render(<ImageAttachmentPreview image={IMAGE} onRemove={onRemove} />)
    fireEvent.click(screen.getByRole("button", { name: /remove attached image/i }))
    expect(onRemove).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/web && npx vitest run tests/ImageAttachmentPreview.test.tsx
```

Expected: FAIL — "Cannot find module"

- [ ] **Step 3: Implement component**

```tsx
// apps/web/components/ui/ImageAttachmentPreview.tsx
"use client"
import type { ImageAttachment } from "@/lib/types/image"

type Props = {
  image: ImageAttachment
  onRemove: () => void
}

export function ImageAttachmentPreview({ image, onRemove }: Props) {
  return (
    <div className="relative inline-block">
      <img
        src={image.url}
        alt="Attached image"
        aria-label="Attached image"
        className="h-16 w-16 rounded-md border object-cover"
      />
      <button
        type="button"
        aria-label="Remove attached image"
        onClick={onRemove}
        className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] text-destructive-foreground"
      >
        ✕
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
cd apps/web && npx vitest run tests/ImageAttachmentPreview.test.tsx
```

Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ui/ImageAttachmentPreview.tsx \
        apps/web/tests/ImageAttachmentPreview.test.tsx
git commit -m "feat(web): add ImageAttachmentPreview shared component"
```

---

## Task 5: `ImageAttachArea` shared component (new)

This combines `ImageInsertButton`, `ImageAttachmentPreview`, and `useImageDrop` into one reusable wrapper used by both ChatComposer and JournalScreen.

**Files:**
- Create: `apps/web/components/ui/ImageAttachArea.tsx`
- Create: `apps/web/tests/ImageAttachArea.test.tsx`

**Interfaces:**
- Consumes: `ImageInsertButton` (Task 2), `ImageAttachmentPreview` (Task 4), `useImageDrop` (Task 3)
- Produces:
  ```ts
  type ImageAttachAreaProps = {
    textareaRef: RefObject<HTMLTextAreaElement>
    attachedImage: ImageAttachment | null
    onAttach: (image: ImageAttachment) => void
    onRemove: () => void
    disabled?: boolean
    isDragging?: boolean  // passed from parent's useImageDrop result
  }
  export function ImageAttachArea(props: ImageAttachAreaProps): JSX.Element
  ```

- [ ] **Step 1: Write failing tests**

```tsx
// apps/web/tests/ImageAttachArea.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createRef } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ImageAttachment } from "@/lib/types/image"
import { ImageAttachArea } from "@/components/ui/ImageAttachArea"

vi.mock("@/lib/imageUpload", () => ({ uploadImage: vi.fn() }))
import { uploadImage } from "@/lib/imageUpload"

const ATTACHMENT: ImageAttachment = {
  url: "/api/images/2026-06-26/x.png",
  path: "/abs/input/2026-06-26/x.png",
}

describe("ImageAttachArea", () => {
  const ref = createRef<HTMLTextAreaElement>()
  afterEach(() => vi.clearAllMocks())

  it("renders + button when no image attached", () => {
    render(
      <ImageAttachArea
        textareaRef={ref}
        attachedImage={null}
        onAttach={vi.fn()}
        onRemove={vi.fn()}
      />
    )
    expect(screen.getByRole("button", { name: /attach image/i })).toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("renders thumbnail and remove button when image attached", () => {
    render(
      <ImageAttachArea
        textareaRef={ref}
        attachedImage={ATTACHMENT}
        onAttach={vi.fn()}
        onRemove={vi.fn()}
      />
    )
    expect(screen.getByRole("img", { name: /attached image/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /remove attached image/i })).toBeInTheDocument()
  })

  it("calls onRemove when remove button clicked", () => {
    const onRemove = vi.fn()
    render(
      <ImageAttachArea
        textareaRef={ref}
        attachedImage={ATTACHMENT}
        onAttach={vi.fn()}
        onRemove={onRemove}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: /remove attached image/i }))
    expect(onRemove).toHaveBeenCalledOnce()
  })

  it("calls onAttach after upload via button", async () => {
    vi.mocked(uploadImage).mockResolvedValue(ATTACHMENT)
    const onAttach = vi.fn()
    render(
      <ImageAttachArea
        textareaRef={ref}
        attachedImage={null}
        onAttach={onAttach}
        onRemove={vi.fn()}
      />
    )
    const input = document.querySelector("input[type=file]") as HTMLInputElement
    fireEvent.change(input, {
      target: { files: [new File(["x"], "photo.png", { type: "image/png" })] },
    })
    await waitFor(() => expect(onAttach).toHaveBeenCalledWith(ATTACHMENT))
  })

  it("applies drag ring class when isDragging is true", () => {
    const { container } = render(
      <ImageAttachArea
        textareaRef={ref}
        attachedImage={null}
        onAttach={vi.fn()}
        onRemove={vi.fn()}
        isDragging={true}
      />
    )
    // The wrapper div should contain the drag-ring class
    expect(container.firstChild).toHaveClass("ring-2")
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/web && npx vitest run tests/ImageAttachArea.test.tsx
```

Expected: FAIL — "Cannot find module"

- [ ] **Step 3: Implement `ImageAttachArea`**

```tsx
// apps/web/components/ui/ImageAttachArea.tsx
"use client"
import type { RefObject } from "react"
import type { ImageAttachment } from "@/lib/types/image"
import { ImageInsertButton } from "@/components/ui/ImageInsertButton"
import { ImageAttachmentPreview } from "@/components/ui/ImageAttachmentPreview"

type Props = {
  textareaRef: RefObject<HTMLTextAreaElement>
  attachedImage: ImageAttachment | null
  onAttach: (image: ImageAttachment) => void
  onRemove: () => void
  disabled?: boolean
  isDragging?: boolean
}

export function ImageAttachArea({
  attachedImage,
  onAttach,
  onRemove,
  disabled,
  isDragging,
}: Props) {
  return (
    <div
      className={`flex items-center gap-2 ${isDragging ? "ring-2 ring-primary rounded-md" : ""}`}
    >
      <ImageInsertButton onAttach={onAttach} disabled={disabled} />
      {attachedImage && (
        <ImageAttachmentPreview image={attachedImage} onRemove={onRemove} />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
cd apps/web && npx vitest run tests/ImageAttachArea.test.tsx
```

Expected: 5 tests PASS

- [ ] **Step 5: Run full suite**

```bash
cd apps/web && npx vitest run
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/ui/ImageAttachArea.tsx apps/web/tests/ImageAttachArea.test.tsx
git commit -m "feat(web): add ImageAttachArea shared component"
```

---

## Task 6: Integrate into `ChatComposer` + remove `insertAtCursor`

**Files:**
- Modify: `apps/web/components/chat/ChatComposer.tsx`
- Delete: `apps/web/lib/insertAtCursor.ts`
- Delete: `apps/web/tests/insertAtCursor.test.ts`

**Interfaces:**
- Consumes: `ImageAttachArea` (Task 5), `useImageDrop` (Task 3), `ImageAttachment` type (Task 1)
- The `onSend` caller in `ChatForm.tsx` or parent must accept `image_path?: string` in the POST body — check how `ChatComposer` calls `onSend` and update accordingly

- [ ] **Step 1: Read `ChatComposer` and its callers**

```bash
grep -n "onSend\|image_path\|ChatComposer" apps/web/components/screens/ChatForm.tsx 2>/dev/null | head -20
grep -rn "ChatComposer\|onSend" apps/web/components/ apps/web/app/ | grep -v node_modules | head -20
```

- [ ] **Step 2: Rewrite `ChatComposer.tsx`**

```tsx
// apps/web/components/chat/ChatComposer.tsx
"use client"
import { useState, useRef, type KeyboardEvent } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ImageAttachArea } from "@/components/ui/ImageAttachArea"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import type { ImageAttachment } from "@/lib/types/image"

type Props = {
  input: string
  setInput: (value: string) => void
  busy: boolean
  supportsMic: boolean
  listening: boolean
  onToggleMic: (prefix: string) => void
  onSend: (imagePath?: string) => void
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
  const [attachedImage, setAttachedImage] = useState<ImageAttachment | null>(null)
  const { isDragging } = useImageDrop(textareaRef, setAttachedImage)

  function handleSend() {
    const path = attachedImage?.path
    setAttachedImage(null)
    onSend(path)
  }

  return (
    <Card>
      <CardContent className="space-y-2 pt-6">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            aria-label="Chat message"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onCompositionStart={() => { composingRef.current = true }}
            onCompositionEnd={() => { composingRef.current = false }}
            onKeyDown={(e) => {
              if (composingRef.current || e.nativeEvent.isComposing) return
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSend()
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
              onClick={handleSend}
              disabled={input.trim().length === 0}
              data-testid="send-button"
            >
              Send
            </Button>
          )}
        </div>
        <ImageAttachArea
          textareaRef={textareaRef}
          attachedImage={attachedImage}
          onAttach={setAttachedImage}
          onRemove={() => setAttachedImage(null)}
          disabled={busy}
          isDragging={isDragging}
        />
        {!supportsMic && (
          <p className="text-xs text-muted-foreground" data-testid="mic-unsupported">
            Voice input is unavailable in this browser (Chrome / Edge supported).
          </p>
        )}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 3: Update callers of `onSend` to accept optional `imagePath`**

Find where `ChatComposer` is rendered and `onSend` is defined. Update the call to pass `image_path` in the POST body:

```bash
grep -rn "onSend\|ChatComposer" apps/web/components/ apps/web/app/ | grep -v node_modules | grep -v ".test."
```

In whichever file defines `onSend` for the chat, update the POST body from:
```ts
body: JSON.stringify({ date, question: input })
```
to:
```ts
body: JSON.stringify({ date, question: input, ...(imagePath ? { image_path: imagePath } : {}) })
```

And update the `onSend` signature in that file from `() => void` to `(imagePath?: string) => void`.

- [ ] **Step 4: Delete unused files**

```bash
rm apps/web/lib/insertAtCursor.ts apps/web/tests/insertAtCursor.test.ts
```

- [ ] **Step 5: Run full suite**

```bash
cd apps/web && npx vitest run
```

Expected: all PASS (insertAtCursor tests gone, rest pass)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(web): integrate ImageAttachArea into ChatComposer; pass image_path on send"
```

---

## Task 7: Integrate into `JournalScreen`

**Files:**
- Modify: `apps/web/components/screens/JournalScreen.tsx`

**Interfaces:**
- Consumes: `ImageAttachArea` (Task 5), `useImageDrop` (Task 3), `ImageAttachment` type (Task 1)
- Two independent attach areas: one for "Record today" textarea, one for Brainstorm textarea
- "Record today" does NOT send to Claude — `image_path` is only relevant for the Brainstorm section

- [ ] **Step 1: Read the current Brainstorm send call**

```bash
grep -n "brainstorm\|fetch\|journal/chat\|question\|image" apps/web/components/screens/JournalScreen.tsx | head -30
```

- [ ] **Step 2: Add imports and state to `JournalScreen.tsx`**

Add these imports near the top (after existing imports):

```ts
import { ImageAttachArea } from "@/components/ui/ImageAttachArea"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import type { ImageAttachment } from "@/lib/types/image"
```

Add state and refs near the existing `composeRef` and `brainstormRef` declarations:

```ts
const brainstormRef = useRef<HTMLTextAreaElement>(null)

const [composeImage, setComposeImage] = useState<ImageAttachment | null>(null)
const [brainstormImage, setBrainstormImage] = useState<ImageAttachment | null>(null)

const { isDragging: isComposeDragging } = useImageDrop(composeRef, setComposeImage)
const { isDragging: isBrainstormDragging } = useImageDrop(brainstormRef, setBrainstormImage)
```

- [ ] **Step 3: Add `ImageAttachArea` below "Record today" textarea**

Find the section after the "Record today" `</textarea>` closing tag and add before the Save button div:

```tsx
<ImageAttachArea
  textareaRef={composeRef}
  attachedImage={composeImage}
  onAttach={setComposeImage}
  onRemove={() => setComposeImage(null)}
  disabled={saving}
  isDragging={isComposeDragging}
/>
```

Also add drag ring to the textarea className: append `${isComposeDragging ? " ring-2 ring-primary" : ""}`.

- [ ] **Step 4: Add `ref` and `ImageAttachArea` to Brainstorm textarea**

Add `ref={brainstormRef}` to the brainstorm textarea element.

Add drag ring: append `${isBrainstormDragging ? " ring-2 ring-primary" : ""}` to className.

After the Brainstorm `</textarea>`, add:

```tsx
<ImageAttachArea
  textareaRef={brainstormRef}
  attachedImage={brainstormImage}
  onAttach={setBrainstormImage}
  onRemove={() => setBrainstormImage(null)}
  isDragging={isBrainstormDragging}
/>
```

- [ ] **Step 5: Update brainstorm send to include `image_path`**

Find the `brainstorm()` function call that does `fetch("/api/journal/chat", ...)`. Update the body:

```ts
body: JSON.stringify({
  question,
  days: 7,
  ...(brainstormImage ? { image_path: brainstormImage.path } : {}),
})
```

After the fetch call completes (success or error), clear the image:

```ts
setBrainstormImage(null)
```

- [ ] **Step 6: Run full suite**

```bash
cd apps/web && npx vitest run
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/screens/JournalScreen.tsx
git commit -m "feat(web): integrate ImageAttachArea into JournalScreen compose + brainstorm"
```

---

## Task 8: Python `run_claude_with_image` in `claude_runner.py`

**Files:**
- Modify: `apps/python/src/claude_runner.py`
- Modify: `apps/python/tests/test_claude_runner.py`

**Interfaces:**
- Produces:
  ```python
  def run_claude_with_image(
      prompt: str,
      image_path: str,
      label: str,
      timeout: int = 300,
      max_attempts: int = RETRY_MAX_ATTEMPTS,
  ) -> str:
      """Invoke claude CLI with a vision content block piped via stdin.
      Returns text result. Raises RuntimeError on failure."""
  ```

- [ ] **Step 1: Write failing tests**

Add to `apps/python/tests/test_claude_runner.py`:

```python
import base64
import json
from pathlib import Path

class TestRunClaudeWithImage:
    def test_builds_multimodal_stdin_and_returns_result(self, tmp_path, monkeypatch):
        """run_claude_with_image encodes the image and pipes JSON to claude stdin."""
        img_file = tmp_path / "photo.png"
        img_file.write_bytes(b"PNG_DATA")
        expected_b64 = base64.b64encode(b"PNG_DATA").decode()

        captured = {}

        def fake_run(cmd, *, input=None, capture_output, text, timeout, env, **kw):
            captured["input"] = input
            captured["cmd"] = cmd
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"result": "nice image!", "usage": {}})
            return result

        monkeypatch.setattr("src.claude_runner.subprocess.run", fake_run)
        monkeypatch.setattr("src.claude_runner.shutil.which", lambda _: "/usr/bin/claude")

        from src.claude_runner import run_claude_with_image
        text = run_claude_with_image("What is this?", str(img_file), "test-vision")

        assert text == "nice image!"
        msg = json.loads(captured["input"])
        assert msg["role"] == "user"
        content = msg["content"]
        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["media_type"] == "image/png"
        assert content[0]["source"]["data"] == expected_b64
        assert content[1]["type"] == "text"
        assert content[1]["text"] == "What is this?"
        # Must use -p - (read prompt from stdin)
        assert "-p" in captured["cmd"]
        assert "-" in captured["cmd"]

    def test_raises_on_nonzero_returncode(self, tmp_path, monkeypatch):
        img_file = tmp_path / "photo.png"
        img_file.write_bytes(b"data")

        def fake_run(cmd, *, input=None, **kw):
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            result.stderr = "vision not supported"
            return result

        monkeypatch.setattr("src.claude_runner.subprocess.run", fake_run)
        monkeypatch.setattr("src.claude_runner.shutil.which", lambda _: "/usr/bin/claude")

        from src.claude_runner import run_claude_with_image
        with pytest.raises(RuntimeError, match="vision not supported"):
            run_claude_with_image("Q", str(img_file), "test")

    def test_raises_if_image_file_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.claude_runner.shutil.which", lambda _: "/usr/bin/claude")

        from src.claude_runner import run_claude_with_image
        with pytest.raises((FileNotFoundError, OSError)):
            run_claude_with_image("Q", str(tmp_path / "missing.png"), "test")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/python && .venv/bin/pytest tests/test_claude_runner.py::TestRunClaudeWithImage -v
```

Expected: FAIL — `ImportError: cannot import name 'run_claude_with_image'`

- [ ] **Step 3: Add `run_claude_with_image` to `claude_runner.py`**

Add these imports at the top of the file (after existing imports):

```python
import base64
```

Add the function after `run_claude`:

```python
_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def run_claude_with_image(
    prompt: str,
    image_path: str,
    label: str,
    timeout: int = 300,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
) -> str:
    """Invoke claude CLI with a vision content block piped via stdin.

    Encodes the image at ``image_path`` as base64 and builds a multimodal
    JSON message compatible with the Claude Messages API format. The message
    is piped to ``claude -p -`` which reads the prompt from stdin.
    Works with cli (OAuth) auth — no API key required.
    """
    claude_path = shutil.which("claude")
    if claude_path is None:
        raise RuntimeError("claude CLI not found. Check your PATH.")

    img_bytes = Path(image_path).read_bytes()
    b64 = base64.b64encode(img_bytes).decode()
    ext = Path(image_path).suffix.lstrip(".").lower()
    media_type = _MEDIA_TYPES.get(ext, "image/png")

    message = json.dumps({
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            },
            {"type": "text", "text": prompt},
        ],
    })

    env = build_env(auth_mode=state_mod.read_state().auth_mode)
    model = get_model()
    cmd = [
        claude_path, "-p", "-",
        "--output-format", "json",
        "--model", model,
    ]

    logger.info("claude vision call start: %s (timeout=%ds)", label, timeout)
    result = subprocess.run(
        cmd,
        input=message,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )

    if result.returncode != 0:
        logger.error(
            "claude vision error [%s] rc=%d\nstderr=%s",
            label, result.returncode, result.stderr,
        )
        raise RuntimeError(result.stderr or result.stdout or "claude vision call failed")

    logger.info("claude vision done: %s (%d chars)", label, len(result.stdout))
    return _parse_and_log_usage(result.stdout, label)
```

Also add `from pathlib import Path` if not already present at top of file (check first with `grep "from pathlib" apps/python/src/claude_runner.py`).

- [ ] **Step 4: Run tests**

```bash
cd apps/python && .venv/bin/pytest tests/test_claude_runner.py::TestRunClaudeWithImage -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Run full Python suite**

```bash
cd apps/python && .venv/bin/pytest -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add apps/python/src/claude_runner.py apps/python/tests/test_claude_runner.py
git commit -m "feat(python): add run_claude_with_image for Claude vision via stdin JSON"
```

---

## Task 9: Python chat router — `image_path` support + security validation

**Files:**
- Modify: `apps/python/web/routers/chat.py`
- Modify: `apps/python/tests/test_api_chat.py`
- Modify: `apps/python/tests/test_api_journal_chat.py`

**Interfaces:**
- Consumes: `run_claude_with_image` from `src.claude_runner` (Task 8)
- `ChatBody` gains `image_path: str | None = None`
- `JournalChatBody` gains `image_path: str | None = None`
- Security: `image_path` must resolve inside `IMAGES_ROOT` (same pattern as the Next.js serve route)

- [ ] **Step 1: Determine `IMAGES_ROOT` in chat.py**

`REPO_ROOT` is already defined in `chat.py` as `Path(__file__).resolve().parents[4]`. Add:

```python
IMAGES_ROOT = REPO_ROOT / "apps" / "python" / "input" / "images"
```

- [ ] **Step 2: Write failing tests**

Add to `apps/python/tests/test_api_chat.py`:

```python
class TestChatVision:
    def test_post_chat_with_image_path_calls_vision(self, tmp_path, client, monkeypatch):
        """POST /api/chat with image_path routes to run_claude_with_image."""
        # Create a fake image file inside the allowed images root
        images_root = Path(__file__).resolve().parents[3] / "apps" / "python" / "input" / "images"
        date_dir = images_root / "2026-06-26"
        date_dir.mkdir(parents=True, exist_ok=True)
        img = date_dir / "test.png"
        img.write_bytes(b"PNG")

        called_with = {}

        def fake_popen(cmd, *, stdout, stderr, stdin, env, **kw):
            called_with["stdin_mode"] = stdin
            called_with["cmd"] = cmd
            proc = MagicMock()
            proc.stdout = io.BytesIO(_delta_line("good answer") + _result_line(result="good answer"))
            proc.stderr = MagicMock()
            proc.stderr.read.return_value = b""
            proc.returncode = 0
            proc.wait.return_value = 0
            proc.__enter__ = lambda s: s
            proc.__exit__ = MagicMock(return_value=False)
            return proc

        monkeypatch.setattr("src.chat_session.subprocess.Popen", fake_popen)
        monkeypatch.setattr("web.routers.chat.subprocess.Popen", fake_popen)

        resp = client.post(
            "/api/chat",
            json={"date": "2026-06-26", "question": "What is this?", "image_path": str(img)},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 202
        # stdin should be PIPE not DEVNULL when image_path provided
        import subprocess as sp
        assert called_with.get("stdin_mode") == sp.PIPE

    def test_post_chat_rejects_traversal_image_path(self, client):
        """image_path outside images root is rejected with 400."""
        resp = client.post(
            "/api/chat",
            json={"date": "2026-06-26", "question": "Q", "image_path": "/etc/passwd"},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 400
        assert "Invalid image path" in resp.json()["detail"]
```

Add similar tests to `test_api_journal_chat.py` for `POST /api/journal/chat`:

```python
class TestJournalChatVision:
    def test_journal_chat_with_image_path_rejected_on_traversal(self, client):
        resp = client.post(
            "/api/journal/chat",
            json={"question": "Q", "image_path": "/etc/passwd"},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 400
        assert "Invalid image path" in resp.json()["detail"]
```

- [ ] **Step 3: Run to verify failure**

```bash
cd apps/python && .venv/bin/pytest tests/test_api_chat.py::TestChatVision tests/test_api_journal_chat.py::TestJournalChatVision -v
```

Expected: FAIL — fields not recognized yet

- [ ] **Step 4: Update `ChatBody`, `JournalChatBody`, and routing in `chat.py`**

Add `IMAGES_ROOT` constant after `PYTHON_APP`:

```python
IMAGES_ROOT = REPO_ROOT / "apps" / "python" / "input" / "images"
```

Add `image_path` field to both models:

```python
class ChatBody(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    question: str = Field(min_length=1)
    image_path: str | None = None


class JournalChatBody(BaseModel):
    question: str = Field(min_length=1)
    days: int = Field(default=7, ge=1, le=31)
    image_path: str | None = None
```

Add a security validator function:

```python
def _validate_image_path(image_path: str | None) -> Path | None:
    """Validate that image_path is inside IMAGES_ROOT. Returns resolved Path or None."""
    if image_path is None:
        return None
    resolved = Path(image_path).resolve()
    if not str(resolved).startswith(str(IMAGES_ROOT) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid image path")
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Image file not found")
    return resolved
```

Update `_run_chat_job` to accept optional `image_message: str | None`:

```python
def _run_chat_job(
    job_id: str,
    cmd: list[str],
    session_file: Path,
    env: dict[str, str],
    label: str,
    image_message: str | None = None,
) -> None:
    ...
    # In the Popen call, change stdin handling:
    stdin_mode = subprocess.PIPE if image_message else subprocess.DEVNULL
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=stdin_mode,
        env=env,
    )
    if image_message:
        proc.stdin.write(image_message.encode())
        proc.stdin.close()
    ...
```

Update `post_chat` to build `image_message` and pass it:

```python
@router.post("/chat", status_code=202, response_model=ChatPostResponse)
def post_chat(body: ChatBody, background_tasks: BackgroundTasks) -> ChatPostResponse:
    img_path = _validate_image_path(body.image_path)
    ...
    image_message: str | None = None
    if img_path:
        import base64 as _b64
        b64 = _b64.b64encode(img_path.read_bytes()).decode()
        ext = img_path.suffix.lstrip(".").lower()
        media = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png",
                 "gif":"image/gif","webp":"image/webp"}.get(ext, "image/png")
        image_message = json.dumps({
            "role": "user",
            "content": [
                {"type":"image","source":{"type":"base64","media_type":media,"data":b64}},
                {"type":"text","text":body.question},
            ],
        })
        # Use -p - to read prompt from stdin
        cmd = [*build_cmd(body.date, briefing_file, session_file), "-p", "-", *CHAT_STREAM_FLAGS]
    else:
        cmd = [*build_cmd(body.date, briefing_file, session_file), "-p", body.question, *CHAT_STREAM_FLAGS]

    job = chat_job_store.create_job()
    background_tasks.add_task(_run_chat_job, job.job_id, cmd, session_file, env, "chat", image_message)
    return ChatPostResponse(job_id=job.job_id, status=job.status)
```

Apply the same pattern to `post_journal_chat`.

- [ ] **Step 5: Run tests**

```bash
cd apps/python && .venv/bin/pytest tests/test_api_chat.py tests/test_api_journal_chat.py -v
```

Expected: all PASS

- [ ] **Step 6: Run full Python suite**

```bash
cd apps/python && .venv/bin/pytest -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add apps/python/web/routers/chat.py \
        apps/python/tests/test_api_chat.py \
        apps/python/tests/test_api_journal_chat.py
git commit -m "feat(python): add image_path vision support to chat and journal/chat endpoints"
```

---

## Task 10: Manual integration test + PR

- [ ] **Step 1: Run all tests**

```bash
cd apps/web && npx vitest run
cd apps/python && .venv/bin/pytest -v
```

Expected: all green

- [ ] **Step 2: Start dev server**

```bash
cd apps/web && npm run dev
# In another terminal:
cd apps/python && .venv/bin/uvicorn web.app:app --reload --port 8000
```

- [ ] **Step 3: Test QA chat vision**

1. Navigate to `http://localhost:3001` → QA Chat
2. Click "+" → select a PNG image
3. Verify thumbnail appears below textarea with ✕ button
4. Type "この画像を説明してください" → Send
5. Verify Claude responds with image content (not "画像を読み取る権限がありません")
6. Verify attached image clears after send

- [ ] **Step 4: Test D&D in chat**

1. Drag a PNG onto the chat textarea
2. Verify border highlights (ring-2 ring-primary) while dragging
3. Verify browser does NOT navigate to a new tab
4. Verify thumbnail appears after drop

- [ ] **Step 5: Test Journal Brainstorm vision**

1. Navigate to Journal
2. Click "+" below Brainstorm textarea → attach an image
3. Type "この画像について何か考えてください" → Brainstorm
4. Verify Claude answers with vision-aware response

- [ ] **Step 6: Test error cases**

1. Try `.pdf` file → error "File type ".pdf" is not allowed"
2. Try `image_path` of `/etc/passwd` via direct API call → 400 "Invalid image path"

- [ ] **Step 7: Create PR**

```bash
git push -u origin feat/issue-308-image-insert-component
gh pr create \
  --title "feat: image vision — attach images to chat/journal prompts for Claude to see" \
  --body "$(cat <<'EOF'
## Summary

- Upload images via "+" button or drag-and-drop (D&D bug fixed: dragenter+stopPropagation)
- Shared `ImageAttachArea` component used in ChatComposer and JournalScreen
- Python backend encodes image as base64 and pipes multimodal JSON to `claude -p -`
- Claude receives the image as a vision content block and responds with image-aware answers
- Works with cli (OAuth) auth — no API key or additional billing required

## Test plan

- [ ] `cd apps/web && npx vitest run` — all pass
- [ ] `cd apps/python && .venv/bin/pytest -v` — all pass
- [ ] QA chat: attach image → Claude describes it correctly
- [ ] QA chat: D&D no longer opens image in new tab
- [ ] Journal Brainstorm: same vision behavior
- [ ] Invalid path rejected with 400

Closes #311
EOF
)"
```
