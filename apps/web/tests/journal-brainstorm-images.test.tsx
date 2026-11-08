import { createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// A brainstorm needs at least one recent entry to read (#589), so these
// tests start from a journal that already has one.
const EARLIER_ENTRY = { id: "2026-11-01_080000", date: "2026-11-01", size: 40, item: "Earlier note", notion_url: "" }

import { JournalSidebarList } from "@/components/journal/JournalSidebarList"
import { JournalScreen } from "@/components/screens/JournalScreen"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"
import { JournalNavProvider } from "@/lib/journalNavStore"
import { MAX_IMAGES_PER_MESSAGE } from "@/lib/types/image"

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

function renderJournal() {
  render(
    <JournalChatStateProvider>
      <JournalChatJobStateProvider>
        <JournalNavProvider>
          <JournalSidebarList />
          <JournalScreen />
        </JournalNavProvider>
      </JournalChatJobStateProvider>
    </JournalChatStateProvider>,
  )
  fireEvent.click(screen.getByRole("button", { name: /new/i }))
  const box = screen.getByPlaceholderText(/what should i focus on next/i)
  fireEvent.change(box, { target: { value: "ideas?" } })
  return box
}

function pasteImages(el: Element, names: string[]) {
  const files = names.map((n) => new File([n], n, { type: "image/png" }))
  fireEvent(el, createEvent.paste(el, { clipboardData: { files, getData: () => "" } }))
}

const previews = () => screen.queryAllByRole("img", { name: "Attached image" })

describe("journal brainstorm images", () => {
  const fetchMock = vi.fn()
  let chatBodies: Array<Record<string, unknown>>

  beforeEach(() => {
    window.sessionStorage.clear()
    chatBodies = []
    vi.stubGlobal("fetch", fetchMock)
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === "/api/journal" && (!init?.method || init.method === "GET")) {
        return jsonResponse({ entries: [EARLIER_ENTRY] })
      }
      if (url === "/api/images/upload") {
        const file = (init!.body as FormData).get("file") as File
        return jsonResponse({ url: `/api/images/${file.name}`, path: `/abs/${file.name}` })
      }
      if (url === "/api/journal/chat") {
        chatBodies.push(JSON.parse(init!.body as string))
        return jsonResponse({ job_id: "brainstorm-1" }, 202)
      }
      if (url === "/api/chat/brainstorm-1/stream") {
        return new Response("data: thoughts\n\n", {
          headers: { "content-type": "text/event-stream" },
        })
      }
      return jsonResponse({}, 404)
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    window.sessionStorage.clear()
  })

  it("adds pasted images and sends them all with the brainstorm", async () => {
    const box = renderJournal()
    pasteImages(box, ["first.png", "second.png"])
    await waitFor(() => expect(previews()).toHaveLength(2))
    pasteImages(box, ["third.png"])
    await waitFor(() => expect(previews()).toHaveLength(3))

    fireEvent.click(screen.getByRole("button", { name: "Brainstorm" }))

    await waitFor(() => expect(chatBodies).toHaveLength(1))
    expect(chatBodies[0].image_paths).toEqual(["/abs/first.png", "/abs/second.png", "/abs/third.png"])
    await waitFor(() => expect(previews()).toHaveLength(0))
  })

  it("removes one image by position before sending", async () => {
    const box = renderJournal()
    pasteImages(box, ["first.png", "second.png"])
    await waitFor(() => expect(previews()).toHaveLength(2))
    fireEvent.click(screen.getByRole("button", { name: "Remove attached image 2" }))
    await waitFor(() => expect(previews()).toHaveLength(1))

    fireEvent.click(screen.getByRole("button", { name: "Brainstorm" }))
    await waitFor(() => expect(chatBodies).toHaveLength(1))
    expect(chatBodies[0].image_paths).toEqual(["/abs/first.png"])
  })

  it("sends no image field without attachments", async () => {
    renderJournal()
    fireEvent.click(screen.getByRole("button", { name: "Brainstorm" }))
    await waitFor(() => expect(chatBodies).toHaveLength(1))
    expect(chatBodies[0]).not.toHaveProperty("image_paths")
    expect(chatBodies[0]).not.toHaveProperty("image_path")
  })

  it("refuses images past the limit and says so", async () => {
    const box = renderJournal()
    pasteImages(
      box,
      Array.from({ length: MAX_IMAGES_PER_MESSAGE + 1 }, (_, i) => `${i}.png`),
    )
    expect(await screen.findByTestId("attach-error")).toHaveTextContent(
      `Up to ${MAX_IMAGES_PER_MESSAGE} images per message`,
    )
    expect(previews()).toHaveLength(MAX_IMAGES_PER_MESSAGE)
  })

  it("holds back the brainstorm while a picked image uploads", async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((r) => { release = r })
    const base = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/images/upload") await gate
      return base(input, init)
    })
    renderJournal()
    const picker = document.querySelector(
      'input[accept="image/jpeg,image/png,image/gif,image/webp"]'
    ) as HTMLInputElement
    fireEvent.change(picker, {
      target: { files: [new File(["p"], "picked.png", { type: "image/png" })] },
    })
    const button = screen.getByRole("button", { name: "Brainstorm" })
    await waitFor(() => expect(button).toBeDisabled())
    release()
    await waitFor(() => expect(previews()).toHaveLength(1))
    expect(button).toBeEnabled()
    fireEvent.click(button)
    await waitFor(() => expect(chatBodies).toHaveLength(1))
    expect(chatBodies[0].image_paths).toEqual(["/abs/picked.png"])
  })

  it("uses the shared rounded composer without the chat's history toggle", () => {
    renderJournal()
    expect(screen.getByTestId("chat-input")).toHaveAttribute(
      "placeholder",
      expect.stringMatching(/what should i focus on next/i),
    )
    expect(screen.getByRole("button", { name: "Brainstorm" })).toHaveAttribute(
      "data-testid",
      "send-button",
    )
    expect(screen.queryByTestId("search-history-toggle")).toBeNull()
  })
})
