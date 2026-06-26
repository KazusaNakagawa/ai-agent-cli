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
