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
