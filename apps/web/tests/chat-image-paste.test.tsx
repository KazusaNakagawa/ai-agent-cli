import { act, createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ChatComposer } from "@/components/chat/ChatComposer"
import { uploadImage } from "@/lib/imageUpload"
import { MAX_IMAGES_PER_MESSAGE } from "@/lib/types/image"

vi.mock("@/lib/imageUpload", () => ({ uploadImage: vi.fn() }))

const upload = vi.mocked(uploadImage)

const image = (name = "a.png") => new File(["x"], name, { type: "image/png" })
const pdf = () => new File(["x"], "a.pdf", { type: "application/pdf" })
// Each upload resolves to an attachment named after the file it was given.
const attachmentFor = (file: File) => ({ url: `/api/images/${file.name}`, path: `/tmp/${file.name}` })

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

const previews = () => screen.queryAllByRole("img", { name: "Attached image" })
const expectPreviews = (count: number) => waitFor(() => expect(previews()).toHaveLength(count))
const send = () => fireEvent.click(screen.getByTestId("send-button"))

describe("pasting into the chat composer", () => {
  beforeEach(() => {
    upload.mockReset()
    upload.mockImplementation(async (file) => attachmentFor(file))
  })

  it("attaches a pasted image and sends it with the message", async () => {
    const { onSend, textarea } = setup("look at this")
    paste(textarea, [image()])
    await expectPreviews(1)
    send()
    expect(onSend).toHaveBeenCalledWith(["/tmp/a.png"])
  })

  it("sends no images when none are attached", () => {
    const { onSend } = setup("plain question")
    send()
    expect(onSend).toHaveBeenCalledWith([])
  })

  it("leaves a text paste alone", () => {
    const { textarea } = setup()
    expect(paste(textarea, [], "hello")).toBe(true)
    expect(upload).not.toHaveBeenCalled()
  })

  it("attaches the image and keeps the text of a mixed paste", async () => {
    const { textarea } = setup()
    expect(paste(textarea, [image()], "caption")).toBe(true)
    await expectPreviews(1)
  })

  it("ignores a pasted file that is not an image", () => {
    const { textarea } = setup()
    paste(textarea, [pdf()])
    expect(upload).not.toHaveBeenCalled()
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

  it("attaches every image in one paste, in clipboard order", async () => {
    const { onSend, textarea } = setup("two")
    paste(textarea, [image("first.png"), pdf(), image("second.png")])
    await expectPreviews(2)
    expect(upload).toHaveBeenCalledTimes(2)
    send()
    expect(onSend).toHaveBeenCalledWith(["/tmp/first.png", "/tmp/second.png"])
  })

  it("adds a second paste instead of replacing the first", async () => {
    const { onSend, textarea } = setup("two")
    paste(textarea, [image("first.png")])
    await expectPreviews(1)
    paste(textarea, [image("second.png")])
    await expectPreviews(2)
    send()
    expect(onSend).toHaveBeenCalledWith(["/tmp/first.png", "/tmp/second.png"])
  })

  it("removes only the image whose remove button was clicked", async () => {
    const { onSend, textarea } = setup("one left")
    paste(textarea, [image("first.png"), image("second.png")])
    await expectPreviews(2)
    fireEvent.click(screen.getByRole("button", { name: "Remove attached image 1" }))
    await expectPreviews(1)
    send()
    expect(onSend).toHaveBeenCalledWith(["/tmp/second.png"])
  })

  it("clears the attachments once the message is sent", async () => {
    const { textarea } = setup("q")
    paste(textarea, [image()])
    await expectPreviews(1)
    send()
    await expectPreviews(0)
  })

  it(`accepts exactly ${MAX_IMAGES_PER_MESSAGE} images without a notice`, async () => {
    const { textarea } = setup()
    paste(textarea, Array.from({ length: MAX_IMAGES_PER_MESSAGE }, (_, i) => image(`${i}.png`)))
    await expectPreviews(MAX_IMAGES_PER_MESSAGE)
    expect(screen.queryByTestId("attach-error")).not.toBeInTheDocument()
  })

  it("refuses images past the limit and says so", async () => {
    const { onSend, textarea } = setup("q")
    paste(textarea, Array.from({ length: MAX_IMAGES_PER_MESSAGE + 1 }, (_, i) => image(`${i}.png`)))
    expect(await screen.findByTestId("attach-error")).toHaveTextContent(
      `Up to ${MAX_IMAGES_PER_MESSAGE} images per message`,
    )
    expect(previews()).toHaveLength(MAX_IMAGES_PER_MESSAGE)
    send()
    expect(onSend.mock.calls[0][0]).toHaveLength(MAX_IMAGES_PER_MESSAGE)
  })

  it("keeps the images that uploaded when another one fails", async () => {
    upload.mockImplementation(async (file) => {
      if (file.name === "bad.png") throw new Error("File too large")
      return attachmentFor(file)
    })
    const { textarea } = setup()
    paste(textarea, [image("good.png"), image("bad.png")])
    expect(await screen.findByTestId("attach-error")).toHaveTextContent("File too large")
    expect(previews()).toHaveLength(1)
  })

  it("clears an upload error on the next paste", async () => {
    upload.mockRejectedValueOnce(new Error("File too large"))
    const { textarea } = setup()
    paste(textarea, [image()])
    await screen.findByTestId("attach-error")
    paste(textarea, [image()])
    await expectPreviews(1)
    expect(screen.queryByTestId("attach-error")).not.toBeInTheDocument()
  })

  it("clears an upload error on send", async () => {
    upload.mockRejectedValueOnce(new Error("File too large"))
    const { textarea } = setup("question")
    paste(textarea, [image()])
    await screen.findByTestId("attach-error")
    send()
    expect(screen.queryByTestId("attach-error")).not.toBeInTheDocument()
  })

  it("holds back sending until every upload settles", async () => {
    let finish: () => void = () => {}
    upload.mockImplementationOnce(
      (file) => new Promise((r) => { finish = () => r(attachmentFor(file)) }),
    )
    const { onSend, textarea } = setup("question")
    paste(textarea, [image("slow.png"), image("fast.png")])
    await waitFor(() => expect(screen.getByTestId("send-button")).toBeDisabled())
    fireEvent.keyDown(textarea, { key: "Enter" })
    expect(onSend).not.toHaveBeenCalled()
    await act(async () => finish())
    expect(screen.getByTestId("send-button")).toBeEnabled()
    fireEvent.keyDown(textarea, { key: "Enter" })
    expect(onSend).toHaveBeenCalledWith(["/tmp/slow.png", "/tmp/fast.png"])
  })
})
