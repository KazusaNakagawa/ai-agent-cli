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
      // jsdom does not support DragEvent or DataTransfer; use a plain Event
      // with dataTransfer injected via Object.defineProperty.
      const dragoverEvent = new Event("dragover", { bubbles: true })
      Object.defineProperty(dragoverEvent, "dataTransfer", {
        value: { types: ["Files"] },
      })
      el.dispatchEvent(dragoverEvent)
    })

    expect(result.current.isDragging).toBe(true)
  })

  it("calls onInsert with snippet on drop", async () => {
    vi.mocked(uploadImage).mockResolvedValue("![image](/api/images/2026-06-26/x.png)")
    const onInsert = vi.fn()
    const ref = { current: el }
    renderHook(() => useImageDrop(ref, onInsert))

    const file = new File(["x"], "photo.png", { type: "image/png" })

    // jsdom does not support DataTransfer.items.add(), so build a minimal mock
    // that satisfies the hook's e.dataTransfer?.files[0] access path.
    const mockDataTransfer = {
      files: [file],
      types: ["Files"],
    }

    await act(async () => {
      // jsdom does not support DragEvent; use a plain Event with dataTransfer injected
      const dropEvent = new Event("drop", { bubbles: true })
      Object.defineProperty(dropEvent, "dataTransfer", { value: mockDataTransfer })
      el.dispatchEvent(dropEvent)
      await Promise.resolve()
    })

    expect(onInsert).toHaveBeenCalledWith("![image](/api/images/2026-06-26/x.png)")
  })
})
