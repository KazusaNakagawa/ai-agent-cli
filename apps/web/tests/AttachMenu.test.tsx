import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AttachMenu } from "@/components/ui/AttachMenu"

vi.mock("@/lib/imageUpload", () => ({ uploadImage: vi.fn() }))
vi.mock("@/lib/fileUpload", () => ({ uploadFile: vi.fn() }))
import { uploadImage } from "@/lib/imageUpload"
import { uploadFile } from "@/lib/fileUpload"

describe("AttachMenu", () => {
  afterEach(() => vi.clearAllMocks())

  it("opens a menu with image and file options", () => {
    render(<AttachMenu onAttachImage={vi.fn()} onInsertFile={vi.fn()} />)
    fireEvent.click(screen.getByRole("button", { name: /attach/i }))
    expect(screen.getByRole("menuitem", { name: /insert image/i })).toBeInTheDocument()
    expect(screen.getByRole("menuitem", { name: /attach file/i })).toBeInTheDocument()
  })

  it("inserts a Markdown link after a file upload", async () => {
    vi.mocked(uploadFile).mockResolvedValue({
      url: "/api/attachments/2026-06-28/abc.csv",
      path: "/abs/x.csv",
      name: "report.csv",
    })
    const onInsertFile = vi.fn()
    render(<AttachMenu onAttachImage={vi.fn()} onInsertFile={onInsertFile} />)
    // The file input accepts the generic allowlist.
    const fileInput = document.querySelector('input[accept=".pdf,.csv,.txt,.md"]') as HTMLInputElement
    fireEvent.change(fileInput, {
      target: { files: [new File(["x"], "report.csv", { type: "text/csv" })] },
    })
    await waitFor(() =>
      expect(onInsertFile).toHaveBeenCalledWith(
        "[report.csv](/api/attachments/2026-06-28/abc.csv)"
      )
    )
  })

  it("attaches an image via the image input", async () => {
    vi.mocked(uploadImage).mockResolvedValue({
      url: "/api/images/2026-06-28/x.png",
      path: "/abs/x.png",
    })
    const onAttachImage = vi.fn()
    render(<AttachMenu onAttachImage={onAttachImage} onInsertFile={vi.fn()} />)
    const imageInput = document.querySelector(
      'input[accept="image/jpeg,image/png,image/gif,image/webp"]'
    ) as HTMLInputElement
    fireEvent.change(imageInput, {
      target: { files: [new File(["x"], "p.png", { type: "image/png" })] },
    })
    await waitFor(() => expect(onAttachImage).toHaveBeenCalled())
  })
})
