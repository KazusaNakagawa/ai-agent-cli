import { act, render, renderHook, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  JOURNAL_CHAT_JOB_STORAGE_KEY as STORAGE_KEY,
  JournalChatJobStateProvider,
  useJournalChatJobState,
} from "@/lib/journalChatJobStore"

type Handler = (init?: RequestInit) => Promise<Response> | Response

// `data` omitted emits an event block with no `data:` field at all — the shape
// a bare control event takes on the wire, distinct from a present-but-empty
// `data:` (a blank source line).
function sseStream(parts: { event?: string; data?: string }[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const p of parts) {
        let chunk = ""
        if (p.event) chunk += `event: ${p.event}\n`
        if (p.data !== undefined) {
          for (const line of p.data.split("\n")) chunk += `data: ${line}\n`
        }
        chunk += "\n"
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
  return new Response(stream, { status: 200 })
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

function pendingSseResponse(): Response {
  return new Response(new ReadableStream<Uint8Array>({ start() {} }), { status: 200 })
}

describe("journalChatJobStore", () => {
  const fetchMock = vi.fn()
  let queues: Record<string, Handler[]>

  function on(url: string, handler: Handler) {
    if (!queues[url]) queues[url] = []
    queues[url].push(handler)
  }

  beforeEach(() => {
    queues = {}
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (url: string | URL, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      const queue = queues[u]
      if (queue && queue.length > 0) return await queue.shift()!(init)
      throw new Error(`Unmocked fetch in journalChatJobStore test: ${u}`)
    })
    vi.stubGlobal("fetch", fetchMock)
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.sessionStorage.clear()
  })

  function wrapper({ children }: { children: ReactNode }) {
    return <JournalChatJobStateProvider>{children}</JournalChatJobStateProvider>
  }

  it("startJob POSTs /api/journal/chat and streams to done", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j1" }, 202))
    on("/api/chat/j1/stream", () => sseStream([{ data: "hello" }, { data: "world" }]))

    const { result } = renderHook(() => useJournalChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q?", targetEntryId: null })
    })
    await waitFor(() => expect(result.current.status).toBe("done"))
    expect(result.current.jobId).toBe("j1")
    expect(result.current.assistantContent).toBe("hello\nworld")
  })

  // Same defect as the Q&A chat store: dropping blank-line events collapses
  // markdown paragraph breaks into a single run-on paragraph.
  it("preserves blank lines so markdown paragraph breaks survive", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j-para" }, 202))
    on("/api/chat/j-para/stream", () =>
      sseStream([{ data: "First." }, { data: "" }, { data: "Second." }]),
    )

    const { result } = renderHook(() => useJournalChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q?", targetEntryId: null })
    })
    await waitFor(() => expect(result.current.status).toBe("done"))
    expect(result.current.assistantContent).toBe("First.\n\nSecond.")
  })

  // Typed control events carry no `data:` field at all, so they survive the
  // parser's empty-block filter for a different reason than blank lines do.
  // Interleaving both checks that the `ev.type !== "message"` guard still
  // keeps them out of the answer while paragraph breaks are preserved.
  it("ignores typed control events while preserving blank lines around them", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j-mixed" }, 202))
    on("/api/chat/j-mixed/stream", () =>
      sseStream([
        { data: "First." },
        { data: "" },
        // Bare control event: no `data:` field at all.
        { event: "stale_session" },
        { data: "Second." },
        // Control event carrying data, which is what the backend actually
        // sends — its payload must not leak into the answer either.
        { event: "error", data: "upstream blew up" },
        { data: "" },
        { data: "Third." },
      ]),
    )

    const { result } = renderHook(() => useJournalChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q?", targetEntryId: null })
    })
    await waitFor(() => expect(result.current.status).toBe("done"))
    expect(result.current.assistantContent).toBe("First.\n\nSecond.\n\nThird.")
    expect(result.current.error).toBeNull()
  })

  it("persists only while in-flight, clears on done", async () => {
    let release: (() => void) | null = null
    const gate = new Promise<void>((resolve) => { release = resolve })
    on("/api/journal/chat", () => jsonResponse({ job_id: "live" }, 202))
    on("/api/chat/live/stream", async () => {
      await gate
      return sseStream([{ data: "answer" }])
    })

    const { result } = renderHook(() => useJournalChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q", targetEntryId: null })
    })
    await waitFor(() => expect(result.current.status).toBe("running"))
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeTruthy()

    await act(async () => release!())
    await waitFor(() => expect(result.current.status).toBe("done"))
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it("rehydrates a persisted in-flight snapshot and resumes the GET stream", async () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        jobId: "resume-1",
        status: "running",
        question: "what's new?",
        targetEntryId: "entry-9",
        imagePath: null,
        assistantContent: "",
        error: null,
      }),
    )
    on("/api/chat/resume-1/stream", () => sseStream([{ data: "resumed" }, { data: "tail" }]))

    function Probe() {
      const s = useJournalChatJobState()
      return <div data-testid="content">{s.assistantContent}</div>
    }
    render(
      <JournalChatJobStateProvider>
        <Probe />
      </JournalChatJobStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId("content")).toHaveTextContent("resumed tail"))
  })

  it("cancelJob after jobId arrives DELETEs immediately and resets", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j2" }, 202))
    on("/api/chat/j2/stream", () => pendingSseResponse())
    on("/api/chat/j2", () => new Response(null, { status: 204 }))

    const { result } = renderHook(() => useJournalChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q", targetEntryId: null })
    })
    await waitFor(() => expect(result.current.jobId).toBe("j2"))

    act(() => result.current.cancelJob())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/chat/j2",
        expect.objectContaining({ method: "DELETE" }),
      )
    })
    expect(result.current.status).toBe("idle")
    expect(result.current.jobId).toBeNull()
  })

  it("cancelJob before jobId arrives DELETEs once the id shows up", async () => {
    let releasePost: (r: Response) => void = () => {}
    on("/api/journal/chat", () => new Promise<Response>((resolve) => { releasePost = resolve }))
    on("/api/chat/j3", () => new Response(null, { status: 204 }))

    const { result } = renderHook(() => useJournalChatJobState(), { wrapper })
    let startPromise!: Promise<void>
    act(() => {
      startPromise = result.current.startJob({ question: "Q", targetEntryId: null })
    })
    await waitFor(() => expect(result.current.status).toBe("pending"))

    act(() => result.current.cancelJob())
    releasePost(jsonResponse({ job_id: "j3" }, 202))
    await act(async () => { await startPromise })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/chat/j3",
        expect.objectContaining({ method: "DELETE" }),
      )
    })
    expect(result.current.status).toBe("idle")
  })

  it("setError marks the job failed without clearing assistantContent", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j4" }, 202))
    on("/api/chat/j4/stream", () => sseStream([{ data: "partial" }]))

    const { result } = renderHook(() => useJournalChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q", targetEntryId: null })
    })
    await waitFor(() => expect(result.current.status).toBe("done"))

    act(() => result.current.setError("Auto-save failed (HTTP 500)"))
    expect(result.current.status).toBe("failed")
    expect(result.current.error).toBe("Auto-save failed (HTTP 500)")
    expect(result.current.assistantContent).toBe("partial")
  })
})
