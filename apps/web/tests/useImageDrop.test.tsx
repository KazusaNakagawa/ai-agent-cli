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
