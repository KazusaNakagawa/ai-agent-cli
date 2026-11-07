import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AttachMenu } from "@/components/ui/AttachMenu"

vi.mock("@/lib/imageUpload", () => ({ uploadImage: vi.fn() }))
vi.mock("@/lib/fileUpload", () => ({ uploadFile: vi.fn() }))
import { uploadImage } from "@/lib/imageUpload"
import { uploadFile } from "@/lib/fileUpload"

const imageInput = () =>
  document.querySelector(
    'input[accept="image/jpeg,image/png,image/gif,image/webp"]'
  ) as HTMLInputElement

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

  it("lets the image picker select several files", () => {
    render(<AttachMenu onAttachImage={vi.fn()} onInsertFile={vi.fn()} />)
    expect(imageInput()).toHaveAttribute("multiple")
  })

  it("attaches every selected image, in selection order", async () => {
    vi.mocked(uploadImage).mockImplementation(async (file) => ({
      url: `/api/images/${file.name}`,
      path: `/abs/${file.name}`,
    }))
    const onAttach = vi.fn()
    render(<AttachMenu onAttachImage={onAttach} onInsertFile={vi.fn()} />)
    fireEvent.change(imageInput(), {
      target: {
        files: [
          new File(["a"], "first.png", { type: "image/png" }),
          new File(["b"], "second.png", { type: "image/png" }),
        ],
      },
    })
    await waitFor(() => expect(onAttach).toHaveBeenCalledTimes(2))
    expect(onAttach.mock.calls.map(([img]) => img.path)).toEqual(["/abs/first.png", "/abs/second.png"])
  })

  it("keeps the uploaded images and shows the error when one fails", async () => {
    vi.mocked(uploadImage).mockImplementation(async (file) => {
      if (file.name === "bad.png") throw new Error("Image must be under 5 MB")
      return { url: `/api/images/${file.name}`, path: `/abs/${file.name}` }
    })
    const onAttach = vi.fn()
    render(<AttachMenu onAttachImage={onAttach} onInsertFile={vi.fn()} />)
    fireEvent.change(imageInput(), {
      target: {
        files: [
          new File(["a"], "good.png", { type: "image/png" }),
          new File(["b"], "bad.png", { type: "image/png" }),
        ],
      },
    })
    expect(await screen.findByText("Image must be under 5 MB")).toBeInTheDocument()
    expect(onAttach).toHaveBeenCalledTimes(1)
    expect(onAttach).toHaveBeenCalledWith({ url: "/api/images/good.png", path: "/abs/good.png" })
  })

  it("reports when an image upload starts and settles", async () => {
    let finish: () => void = () => {}
    vi.mocked(uploadImage).mockImplementationOnce(
      () => new Promise((r) => { finish = () => r({ url: "/u.png", path: "/abs/u.png" }) }),
    )
    const onUploadingChange = vi.fn()
    render(<AttachMenu onAttachImage={vi.fn()} onInsertFile={vi.fn()} onUploadingChange={onUploadingChange} />)
    fireEvent.change(imageInput(), {
      target: { files: [new File(["a"], "u.png", { type: "image/png" })] },
    })
    await waitFor(() => expect(onUploadingChange).toHaveBeenLastCalledWith(true))
    finish()
    await waitFor(() => expect(onUploadingChange).toHaveBeenLastCalledWith(false))
  })

  it("reports a generic file upload too, and settles after a failure", async () => {
    vi.mocked(uploadFile).mockRejectedValueOnce(new Error("nope"))
    const onUploadingChange = vi.fn()
    render(<AttachMenu onAttachImage={vi.fn()} onInsertFile={vi.fn()} onUploadingChange={onUploadingChange} />)
    const fileInput = document.querySelector('input[accept=".pdf,.csv,.txt,.md"]') as HTMLInputElement
    fireEvent.change(fileInput, {
      target: { files: [new File(["x"], "r.csv", { type: "text/csv" })] },
    })
    expect(await screen.findByText("nope")).toBeInTheDocument()
    expect(onUploadingChange.mock.calls.map(([v]) => v)).toEqual([true, false])
  })
})
