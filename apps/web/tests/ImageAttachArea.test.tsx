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
