import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { JournalScreen } from "@/components/screens/JournalScreen"
import { JournalSidebarList } from "@/components/journal/JournalSidebarList"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"
import { JournalNavProvider } from "@/lib/journalNavStore"

// A stream that stays open (never closes) so the brainstorm stays in the
// "thinking" state until the test aborts it.
function pendingSseResponse(): Response {
  const stream = new ReadableStream<Uint8Array>({ start() {} })
  return new Response(stream, { status: 200 })
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

function renderJournalScreen() {
  return render(
    <JournalChatStateProvider>
      <JournalChatJobStateProvider>
        <JournalNavProvider>
          <JournalSidebarList />
          <JournalScreen />
        </JournalNavProvider>
      </JournalChatJobStateProvider>
    </JournalChatStateProvider>,
  )
}

describe("JournalScreen brainstorm cancel", () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    window.sessionStorage.clear()
    vi.stubGlobal("fetch", fetchMock)
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === "/api/journal" && (!init || !init.method || init.method === "GET")) {
        return Promise.resolve(jsonResponse({ entries: [] }))
      }
      if (url === "/api/journal/chat") {
        return Promise.resolve(jsonResponse({ job_id: "job-1" }, 202))
      }
      if (url === "/api/chat/job-1/stream") {
        // Reject on abort like a real fetch would.
        return new Promise<Response>((resolve, reject) => {
          const signal = init?.signal
          if (signal) {
            signal.addEventListener("abort", () =>
              reject(new DOMException("aborted", "AbortError")),
            )
          }
          resolve(pendingSseResponse())
        })
      }
      if (url === "/api/chat/job-1" && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(jsonResponse({}, 404))
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    window.sessionStorage.clear()
  })

  it("Stop aborts the stream, deletes the job, and restores the question", async () => {
    renderJournalScreen()
    fireEvent.click(screen.getByRole("button", { name: /new/i }))

    const textarea = screen.getByPlaceholderText(/what should i focus on/i)
    fireEvent.change(textarea, { target: { value: "cancel me" } })
    fireEvent.click(screen.getByRole("button", { name: "Brainstorm" }))

    const stopBtn = await screen.findByRole("button", { name: "Stop" })
    fireEvent.click(stopBtn)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/chat/job-1",
        expect.objectContaining({ method: "DELETE" }),
      )
    })
    // Pending turn dropped, question restored, composer editable again.
    await waitFor(() => {
      expect(screen.queryAllByTestId("journal-chat-thinking")).toHaveLength(0)
      expect((textarea as HTMLTextAreaElement).value).toBe("cancel me")
    })
    expect(screen.queryByText(/failed|error/i)).toBeNull()
  })

  it("cancelling before the job id arrives still DELETEs the job", async () => {
    // Hold the POST response until after Stop is clicked, so cancel runs
    // while jobId is still unknown.
    let releasePost: (r: Response) => void = () => {}
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === "/api/journal" && (!init || !init.method || init.method === "GET")) {
        return Promise.resolve(jsonResponse({ entries: [] }))
      }
      if (url === "/api/journal/chat") {
        return new Promise<Response>((resolve) => {
          releasePost = resolve
        })
      }
      if (url === "/api/chat/job-1" && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(jsonResponse({}, 404))
    })

    renderJournalScreen()
    fireEvent.click(screen.getByRole("button", { name: /new/i }))
    const textarea = screen.getByPlaceholderText(/what should i focus on/i)
    fireEvent.change(textarea, { target: { value: "race me" } })
    fireEvent.click(screen.getByRole("button", { name: "Brainstorm" }))

    const stopBtn = await screen.findByRole("button", { name: "Stop" })
    fireEvent.click(stopBtn)
    // POST resolves only after the cancel — the job id was unknown at cancel time.
    releasePost(jsonResponse({ job_id: "job-1" }, 202))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/chat/job-1",
        expect.objectContaining({ method: "DELETE" }),
      )
      expect((textarea as HTMLTextAreaElement).value).toBe("race me")
    })
  })

  it("Esc cancels the in-flight brainstorm", async () => {
    renderJournalScreen()
    fireEvent.click(screen.getByRole("button", { name: /new/i }))

    const textarea = screen.getByPlaceholderText(/what should i focus on/i)
    fireEvent.change(textarea, { target: { value: "esc me" } })
    fireEvent.click(screen.getByRole("button", { name: "Brainstorm" }))
    await screen.findByRole("button", { name: "Stop" })

    fireEvent.keyDown(window, { key: "Escape" })

    await waitFor(() => {
      expect((textarea as HTMLTextAreaElement).value).toBe("esc me")
      expect(screen.queryByRole("button", { name: "Stop" })).toBeNull()
    })
  })
})
