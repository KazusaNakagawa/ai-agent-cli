import { act, createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ChatComposer } from "@/components/chat/ChatComposer"
import { uploadImage } from "@/lib/imageUpload"

vi.mock("@/lib/imageUpload", () => ({ uploadImage: vi.fn() }))

const upload = vi.mocked(uploadImage)
const ATTACHMENT = { url: "/api/images/a.png", path: "/tmp/a.png" }

const image = (name = "a.png") => new File(["x"], name, { type: "image/png" })
const pdf = () => new File(["x"], "a.pdf", { type: "application/pdf" })

function setup(input = "") {
  const onSend = vi.fn()
  render(
    <ChatComposer
      input={input}
      setInput={vi.fn()}
      busy={false}
      supportsMic={false}
      listening={false}
      onToggleMic={vi.fn()}
      onSend={onSend}
      onCancel={vi.fn()}
      searchHistory={false}
      onToggleSearchHistory={vi.fn()}
    />,
  )
  return { onSend, textarea: screen.getByTestId("chat-input") }
}

// Returns whether the browser's default paste would still run.
function paste(el: Element, files: File[], text = "") {
  const event = createEvent.paste(el, {
    clipboardData: { files, getData: () => text },
  })
  fireEvent(el, event)
  return !event.defaultPrevented
}

const preview = () => screen.findByRole("img")

describe("pasting into the chat composer", () => {
  beforeEach(() => {
    upload.mockReset()
    upload.mockResolvedValue(ATTACHMENT)
  })

  it("attaches a pasted image and sends it with the message", async () => {
    const { onSend, textarea } = setup("look at this")
    const file = image()
    paste(textarea, [file])
    await preview()
    expect(upload).toHaveBeenCalledWith(file)
    fireEvent.click(screen.getByTestId("send-button"))
    expect(onSend).toHaveBeenCalledWith(ATTACHMENT.path)
  })

  it("leaves a text paste alone", () => {
    const { textarea } = setup()
    expect(paste(textarea, [], "hello")).toBe(true)
    expect(upload).not.toHaveBeenCalled()
  })

  it("attaches the image and keeps the text of a mixed paste", async () => {
    const { textarea } = setup()
    expect(paste(textarea, [image()], "caption")).toBe(true)
    await preview()
  })

  it("ignores a pasted file that is not an image", () => {
    const { textarea } = setup()
    paste(textarea, [pdf()])
    expect(upload).not.toHaveBeenCalled()
  })

  it("skips non-image files to find the image", async () => {
    const { textarea } = setup()
    const file = image()
    paste(textarea, [pdf(), file])
    await preview()
    expect(upload).toHaveBeenCalledWith(file)
  })

  it("uploads only the first of several images", async () => {
    const { textarea } = setup()
    const first = image("first.png")
    paste(textarea, [first, image("second.png")])
    await preview()
    expect(upload).toHaveBeenCalledTimes(1)
    expect(upload).toHaveBeenCalledWith(first)
  })

  it("does not throw when the clipboard is unavailable", () => {
    const { textarea } = setup()
    fireEvent.paste(textarea)
    expect(upload).not.toHaveBeenCalled()
  })

  it("ignores a paste outside the composer", () => {
    setup()
    paste(document.body, [image()])
    expect(upload).not.toHaveBeenCalled()
  })

  it("shows why an upload failed and clears it on the next paste", async () => {
    upload.mockRejectedValueOnce(new Error("File too large"))
    const { textarea } = setup()
    paste(textarea, [image()])
    expect(await screen.findByTestId("paste-error")).toHaveTextContent("File too large")
    paste(textarea, [image()])
    await preview()
    expect(screen.queryByTestId("paste-error")).not.toBeInTheDocument()
  })

  it("clears a failed paste's error on send", async () => {
    upload.mockRejectedValueOnce(new Error("File too large"))
    const { textarea } = setup("question")
    paste(textarea, [image()])
    await screen.findByTestId("paste-error")
    fireEvent.click(screen.getByTestId("send-button"))
    expect(screen.queryByTestId("paste-error")).not.toBeInTheDocument()
  })

  it("keeps the newest paste when an earlier upload finishes last", async () => {
    let finishFirst: (v: typeof ATTACHMENT) => void = () => {}
    upload.mockReturnValueOnce(new Promise((r) => { finishFirst = r }))
    upload.mockResolvedValueOnce({ url: "/api/images/b.png", path: "/tmp/b.png" })
    const { onSend, textarea } = setup("question")
    paste(textarea, [image("a.png")])
    paste(textarea, [image("b.png")])
    await screen.findByRole("img")
    await act(async () => finishFirst(ATTACHMENT))
    fireEvent.click(screen.getByTestId("send-button"))
    expect(onSend).toHaveBeenCalledWith("/tmp/b.png")
  })

  it("holds back sending until the upload settles", async () => {
    let finish: (v: typeof ATTACHMENT) => void = () => {}
    upload.mockReturnValueOnce(new Promise((r) => { finish = r }))
    const { onSend, textarea } = setup("question")
    paste(textarea, [image()])
    await waitFor(() => expect(screen.getByTestId("send-button")).toBeDisabled())
    fireEvent.keyDown(textarea, { key: "Enter" })
    expect(onSend).not.toHaveBeenCalled()
    await act(async () => finish(ATTACHMENT))
    expect(screen.getByTestId("send-button")).toBeEnabled()
    fireEvent.keyDown(textarea, { key: "Enter" })
    expect(onSend).toHaveBeenCalledWith(ATTACHMENT.path)
  })
})
