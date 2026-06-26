import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
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

// Dispatch a DragEvent-like event on a target with the given dataTransfer.
function fireDrag(
  type: "dragover" | "dragleave" | "drop",
  target: EventTarget,
  dataTransfer: Record<string, unknown>,
  extra: Record<string, unknown> = {}
) {
  const e = new Event(type, { bubbles: true }) as any
  e.preventDefault = vi.fn()
  e.dataTransfer = dataTransfer
  Object.assign(e, extra)
  // jsdom resolves e.target from dispatch; set it explicitly for containment checks.
  Object.defineProperty(e, "target", { value: target, configurable: true })
  act(() => {
    target.dispatchEvent(e)
  })
  return e
}

describe("useImageDrop", () => {
  let el: HTMLTextAreaElement
  beforeEach(() => { el = makeTextarea() })
  afterEach(() => { el.remove(); vi.clearAllMocks() })

  it("isDragging is false initially", () => {
    const { result } = renderHook(() => useImageDrop({ current: el }, vi.fn()))
    expect(result.current.isDragging).toBe(false)
  })

  it("sets isDragging true on dragover with Files over the textarea", () => {
    const { result } = renderHook(() => useImageDrop({ current: el }, vi.fn()))
    fireDrag("dragover", el, { types: ["Files"] })
    expect(result.current.isDragging).toBe(true)
  })

  it("preventDefaults a file dragover outside the textarea (blocks new-tab nav) but stays inactive", () => {
    const { result } = renderHook(() => useImageDrop({ current: el }, vi.fn()))
    const e = fireDrag("dragover", document.body, { types: ["Files"] })
    expect(e.preventDefault).toHaveBeenCalled()
    expect(result.current.isDragging).toBe(false)
  })

  it("ignores non-file drags", () => {
    const { result } = renderHook(() => useImageDrop({ current: el }, vi.fn()))
    const e = fireDrag("dragover", el, { types: ["text/plain"] })
    expect(e.preventDefault).not.toHaveBeenCalled()
    expect(result.current.isDragging).toBe(false)
  })

  it("calls onAttach with ImageAttachment on drop inside the textarea", async () => {
    vi.mocked(uploadImage).mockResolvedValue(ATTACHMENT)
    const onAttach = vi.fn()
    renderHook(() => useImageDrop({ current: el }, onAttach))

    const file = new File(["x"], "photo.png", { type: "image/png" })
    await act(async () => {
      fireDrag("drop", el, { types: ["Files"], files: [file] })
      await Promise.resolve()
    })

    expect(onAttach).toHaveBeenCalledWith(ATTACHMENT)
  })

  it("does NOT call onAttach when dropping outside the textarea, but blocks default", async () => {
    vi.mocked(uploadImage).mockResolvedValue(ATTACHMENT)
    const onAttach = vi.fn()
    renderHook(() => useImageDrop({ current: el }, onAttach))

    const file = new File(["x"], "photo.png", { type: "image/png" })
    let e: any
    await act(async () => {
      e = fireDrag("drop", document.body, { types: ["Files"], files: [file] })
      await Promise.resolve()
    })

    expect(e.preventDefault).toHaveBeenCalled()
    expect(onAttach).not.toHaveBeenCalled()
  })
})
