import { act, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { JournalChatBridge } from "@/components/journal/JournalChatBridge"
import { JournalChatJobStateProvider, useJournalChatJobState } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider, useJournalChatState } from "@/lib/journalChatStore"

type Handler = (init?: RequestInit) => Promise<Response> | Response

function sseStream(parts: { data: string }[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const p of parts) controller.enqueue(encoder.encode(`data: ${p.data}\n\n`))
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

let latestJob: ReturnType<typeof useJournalChatJobState>
let latestChat: ReturnType<typeof useJournalChatState>

function Probe() {
  latestJob = useJournalChatJobState()
  latestChat = useJournalChatState()
  return null
}

function renderTree() {
  return render(
    <JournalChatStateProvider>
      <JournalChatJobStateProvider>
        <JournalChatBridge />
        <Probe />
      </JournalChatJobStateProvider>
    </JournalChatStateProvider>,
  )
}

describe("JournalChatBridge", () => {
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
      throw new Error(`Unmocked fetch in JournalChatBridge test: ${u}`)
    })
    vi.stubGlobal("fetch", fetchMock)
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.sessionStorage.clear()
  })

  it("creates a new entry, commits the turn, and resets the job when targetEntryId is null", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j1" }, 202))
    on("/api/chat/j1/stream", () => sseStream([{ data: "the answer" }]))
    on("/api/journal", () => jsonResponse({ id: "new-entry" }))

    renderTree()
    await act(async () => {
      await latestJob.startJob({ question: "What now?", targetEntryId: null })
    })

    await waitFor(() => expect(latestChat.turns).toEqual([{ question: "What now?", answer: "the answer" }]))
    expect(latestChat.entryId).toBe("new-entry")
    expect(latestJob.jobId).toBeNull()
    expect(latestJob.status).toBe("idle")
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/journal",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("PATCHes the bound entry when targetEntryId is set", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j2" }, 202))
    on("/api/chat/j2/stream", () => sseStream([{ data: "more" }]))
    on("/api/journal/existing-entry", () => new Response(null, { status: 204 }))

    renderTree()
    await act(async () => {
      await latestJob.startJob({ question: "Follow up", targetEntryId: "existing-entry" })
    })

    await waitFor(() => expect(latestChat.turns).toEqual([{ question: "Follow up", answer: "more" }]))
    expect(latestChat.entryId).toBe("existing-entry")
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/journal/existing-entry",
      expect.objectContaining({ method: "PATCH" }),
    )
  })

  it("marks the job failed and does not commit a turn when the save fails", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j3" }, 202))
    on("/api/chat/j3/stream", () => sseStream([{ data: "answer" }]))
    on("/api/journal", () => new Response("boom", { status: 500 }))

    renderTree()
    await act(async () => {
      await latestJob.startJob({ question: "Q", targetEntryId: null })
    })

    await waitFor(() => expect(latestJob.status).toBe("failed"))
    expect(latestJob.error).toContain("Auto-save failed")
    expect(latestChat.turns).toEqual([])
  })

  it("marks the job failed and does not commit a turn when the PATCH save fails", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j5" }, 202))
    on("/api/chat/j5/stream", () => sseStream([{ data: "answer" }]))
    on("/api/journal/existing-entry", () => new Response("boom", { status: 500 }))

    renderTree()
    await act(async () => {
      await latestJob.startJob({ question: "Q", targetEntryId: "existing-entry" })
    })

    await waitFor(() => expect(latestJob.status).toBe("failed"))
    expect(latestJob.error).toContain("Auto-save failed")
    expect(latestChat.turns).toEqual([])
  })

  it("does not double-save when the done state re-renders", async () => {
    on("/api/journal/chat", () => jsonResponse({ job_id: "j4" }, 202))
    on("/api/chat/j4/stream", () => sseStream([{ data: "once" }]))
    on("/api/journal", () => jsonResponse({ id: "e1" }))

    const { rerender } = renderTree()
    await act(async () => {
      await latestJob.startJob({ question: "Q", targetEntryId: null })
    })
    await waitFor(() => expect(latestChat.turns).toHaveLength(1))

    rerender(
      <JournalChatStateProvider>
        <JournalChatJobStateProvider>
          <JournalChatBridge />
          <Probe />
        </JournalChatJobStateProvider>
      </JournalChatStateProvider>,
    )

    expect(
      fetchMock.mock.calls.filter(([u]) => String(u) === "/api/journal").length,
    ).toBe(1)
  })
})
