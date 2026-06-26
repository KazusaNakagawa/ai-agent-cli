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
