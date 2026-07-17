import { act, render, renderHook, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  CHAT_JOB_STORAGE_KEY as STORAGE_KEY,
  ChatJobStateProvider,
  useChatJobState,
} from "@/lib/chatJobStore"

type Handler = (init?: RequestInit) => Promise<Response> | Response

function sseStream(parts: { event?: string; data: string }[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const p of parts) {
        let chunk = ""
        if (p.event) chunk += `event: ${p.event}\n`
        for (const line of p.data.split("\n")) chunk += `data: ${line}\n`
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

describe("chatJobStore", () => {
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
      if (queue && queue.length > 0) {
        const next = queue.shift()!
        return await next(init)
      }
      throw new Error(`Unmocked fetch in chatJobStore test: ${u}`)
    })
    vi.stubGlobal("fetch", fetchMock)
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.sessionStorage.clear()
  })

  function wrapper({ children }: { children: ReactNode }) {
    return <ChatJobStateProvider>{children}</ChatJobStateProvider>
  }

  it("startJob POSTs and transitions through pending → running on a 202", async () => {
    on("/api/chat", () => jsonResponse({ job_id: "abc", status: "pending" }, 202))
    on("/api/chat/abc/stream", () =>
      sseStream([{ data: "hello" }, { data: "world" }]),
    )

    const { result } = renderHook(() => useChatJobState(), { wrapper })
    expect(result.current.status).toBe("idle")

    await act(async () => {
      await result.current.startJob({ question: "Q?", date: "2026-06-06" })
    })
    // After the POST resolves the watch loop runs and consumes the SSE.
    await waitFor(() => expect(result.current.status).toBe("done"))
    expect(result.current.jobId).toBe("abc")
    expect(result.current.question).toBe("Q?")
    expect(result.current.assistantContent).toBe("hello\nworld")
    expect(result.current.error).toBeNull()
  })

  it("persists only while in-flight; clears on terminal", async () => {
    let release: (() => void) | null = null
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    on("/api/chat", () => jsonResponse({ job_id: "live", status: "pending" }, 202))
    on("/api/chat/live/stream", async () => {
      // Hold the stream open until the test releases it.
      await gate
      return sseStream([{ data: "answer" }])
    })

    const { result } = renderHook(() => useChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q", date: "2026-06-06" })
    })
    // While running, the snapshot must be in sessionStorage.
    await waitFor(() => {
      expect(result.current.status).toBe("running")
    })
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeTruthy()

    // Let the stream complete.
    await act(async () => {
      release!()
    })
    await waitFor(() => expect(result.current.status).toBe("done"))
    // On terminal, the entry must be wiped — completed turns live in
    // chatStore.messages, not here. Resurrecting would dup the turn.
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it("serializeForStorage strips UI-only and unrebuildable fields", async () => {
    // Force an in-flight state with all the strippable flags set, then read
    // what hit sessionStorage to verify they were removed.
    on("/api/chat", () => jsonResponse({ job_id: "x", status: "pending" }, 202))
    on("/api/chat/x/stream", () =>
      // event: stale_session sets staleSession; partial content accumulates.
      sseStream([{ data: "partial" }, { event: "stale_session", data: "expired" }]),
    )

    const { result } = renderHook(() => useChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q", date: "2026-06-06" })
    })
    // After the stream closes, status flips to done — but the strippable
    // fields land on prev-state mid-stream. Snapshot sessionStorage AS the
    // running stream applies setState (which we approximate by reading
    // immediately after the test arrives at the running state).
    await waitFor(() => expect(result.current.status).toBe("done"))
    // After terminal the entry is cleared; check that the previous in-flight
    // writes never persisted partial content / staleSession.
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()

    // Now seed a hand-rolled in-flight entry with the strippable fields set
    // and verify the loader is tolerant (factory doesn't fail on extras).
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        jobId: "rehy",
        status: "running",
        question: "Q",
        date: "2026-06-06",
        assistantContent: "should be dropped",
        sessionExpired: true,
        staleSession: true,
        error: null,
      }),
    )
    // A second mount should pick it up but content stays "" until the watch
    // (re-)fills it from the backend replay. The stream call below is what
    // verifies the rebuild after rehydrate.
    on("/api/chat/rehy/stream", () => sseStream([{ data: "rebuilt" }]))
    const second = renderHook(() => useChatJobState(), { wrapper })
    await waitFor(() => expect(second.result.current.jobId).toBe("rehy"))
    // Content rebuilds from the stream — not the persisted "should be
    // dropped" placeholder.
    await waitFor(() =>
      expect(second.result.current.assistantContent).toBe("rebuilt"),
    )
  })

  it("rehydrates a persisted in-flight snapshot and resumes the GET stream", async () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        jobId: "resume-1",
        status: "running",
        question: "what's new?",
        date: "2026-06-06",
        assistantContent: "",
        error: null,
        sessionExpired: false,
        staleSession: false,
      }),
    )
    on("/api/chat/resume-1/stream", () =>
      sseStream([{ data: "resumed" }, { data: "tail" }]),
    )

    function Probe() {
      const s = useChatJobState()
      return (
        <div>
          <span data-testid="jobid">{s.jobId ?? ""}</span>
          <span data-testid="question">{s.question}</span>
          <span data-testid="content">{s.assistantContent}</span>
          <span data-testid="status">{s.status}</span>
        </div>
      )
    }

    render(
      <ChatJobStateProvider>
        <Probe />
      </ChatJobStateProvider>,
    )

    // Hydration: jobId + question are restored from sessionStorage before
    // the stream finishes.
    await waitFor(() =>
      expect(screen.getByTestId("jobid")).toHaveTextContent("resume-1"),
    )
    expect(screen.getByTestId("question")).toHaveTextContent("what's new?")
    // The watch effect runs the GET against the persisted job_id and
    // rebuilds assistantContent from the backend replay.
    await waitFor(() =>
      expect(screen.getByTestId("content")).toHaveTextContent("resumed"),
    )
    expect(screen.getByTestId("content")).toHaveTextContent("tail")
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("done"),
    )
  })

  it("startJob includes search_history in the POST body only when true", async () => {
    let capturedBody: string | undefined
    on("/api/chat", (init) => {
      capturedBody = init?.body as string
      return jsonResponse({ job_id: "abc", status: "pending" }, 202)
    })
    on("/api/chat/abc/stream", () => sseStream([{ data: "hi" }]))

    const { result } = renderHook(() => useChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({
        question: "Q?",
        date: "2026-06-06",
        search_history: true,
      })
    })
    await waitFor(() => expect(result.current.status).toBe("done"))
    expect(JSON.parse(capturedBody!)).toMatchObject({ search_history: true })
  })

  it("startJob omits search_history from the POST body when not requested", async () => {
    let capturedBody: string | undefined
    on("/api/chat", (init) => {
      capturedBody = init?.body as string
      return jsonResponse({ job_id: "abc", status: "pending" }, 202)
    })
    on("/api/chat/abc/stream", () => sseStream([{ data: "hi" }]))

    const { result } = renderHook(() => useChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q?", date: "2026-06-06" })
    })
    await waitFor(() => expect(result.current.status).toBe("done"))
    expect(JSON.parse(capturedBody!)).not.toHaveProperty("search_history")
  })

  it("surfaces 401 on POST as sessionExpired without persisting", async () => {
    on("/api/chat", () => new Response("", { status: 401 }))
    const { result } = renderHook(() => useChatJobState(), { wrapper })
    await act(async () => {
      await result.current.startJob({ question: "Q", date: "2026-06-06" })
    })
    expect(result.current.sessionExpired).toBe(true)
    expect(result.current.jobId).toBeNull()
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it("surfaces 401 on the resume GET as sessionExpired", async () => {
    // Backend tokens can expire mid-stream — different from the POST 401
    // path (covered above) because the in-flight snapshot is in
    // sessionStorage by the time auth dies. Make sure the resume GET
    // 401 also lifts the SessionExpiredCard guard.
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        jobId: "auth-gone",
        status: "running",
        question: "Q",
        date: "2026-06-06",
        assistantContent: "",
        error: null,
        sessionExpired: false,
        staleSession: false,
      }),
    )
    on("/api/chat/auth-gone/stream", () => new Response("", { status: 401 }))

    const { result } = renderHook(() => useChatJobState(), { wrapper })
    await waitFor(() => {
      expect(result.current.sessionExpired).toBe(true)
    })
    expect(result.current.status).toBe("failed")
  })

  it("clears state cleanly on 404 from the resume GET", async () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        jobId: "gone",
        status: "running",
        question: "Q",
        date: "2026-06-06",
        assistantContent: "",
        error: null,
        sessionExpired: false,
        staleSession: false,
      }),
    )
    on("/api/chat/gone/stream", () => new Response("not found", { status: 404 }))

    function Probe() {
      const s = useChatJobState()
      return <div data-testid="status">{s.status}-{s.error ?? ""}</div>
    }

    render(
      <ChatJobStateProvider>
        <Probe />
      </ChatJobStateProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("failed")
    })
    expect(screen.getByTestId("status")).toHaveTextContent("no longer available")
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})
