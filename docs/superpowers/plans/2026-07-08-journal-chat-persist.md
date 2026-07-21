# Journal Chat State Persistence Across Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the Journal brainstorm chat's turn history and in-flight job alive when the user navigates away from `/journal` and back, so a "Thinking…" exchange is never lost.

**Architecture:** Lift the brainstorm chat's turn history and in-flight job out of `JournalScreen` into two React context providers (`journalChatStore.tsx`, `journalChatJobStore.tsx`) mounted at the `(main)` layout level, plus an always-mounted `JournalChatBridge` component that performs the completion save/commit regardless of which page is currently active — mirroring the existing `chatStore.tsx` + `chatJobStore.tsx` split used by the main Q&A chat.

**Tech Stack:** Next.js (App Router), React (hooks/context), TypeScript, Vitest + Testing Library.

## Global Constraints

- Code comments and docstrings: English only (chat UI text stays as-is; this is a refactor, no user-facing copy changes).
- Reuse `apps/web/lib/sse.ts`'s `readSseEvents`/`parseSseChunk` — do not re-implement SSE parsing.
- Follow the existing `chatStore.tsx` / `chatJobStore.tsx` persistence conventions: `sessionStorage`, versioned storage keys (`...:v1`), hydrate-then-sync `useEffect` pattern, FIFO caps.
- Single global Journal brainstorm session at a time (matches the existing single global main-chat job) — no per-entry concurrent jobs.
- Commit after each task passes its tests.

---

### Task 1: `journalChatStore.tsx` — committed turn history

**Files:**
- Create: `apps/web/lib/journalChatStore.tsx`
- Test: `apps/web/tests/journal-chat-store.test.tsx`

**Interfaces:**
- Produces: `JournalTurn = { question: string; answer: string }`; `JournalChatStateProvider`; `useJournalChatState(): { turns: JournalTurn[]; entryId: string | null; addTurn: (t: JournalTurn) => void; setEntryId: (id: string | null) => void; reset: () => void }`; storage key constant `JOURNAL_CHAT_HISTORY_STORAGE_KEY`.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/tests/journal-chat-store.test.tsx
import { act, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import {
  JOURNAL_CHAT_HISTORY_STORAGE_KEY as STORAGE_KEY,
  JournalChatStateProvider,
  useJournalChatState,
} from "@/lib/journalChatStore"

function wrapper({ children }: { children: ReactNode }) {
  return <JournalChatStateProvider>{children}</JournalChatStateProvider>
}

describe("journalChatStore", () => {
  beforeEach(() => window.sessionStorage.clear())
  afterEach(() => window.sessionStorage.clear())

  it("starts empty, appends turns, and persists them", async () => {
    const { result } = renderHook(() => useJournalChatState(), { wrapper })
    expect(result.current.turns).toEqual([])
    expect(result.current.entryId).toBeNull()

    act(() => {
      result.current.addTurn({ question: "Q1", answer: "A1" })
      result.current.setEntryId("entry-1")
    })

    expect(result.current.turns).toEqual([{ question: "Q1", answer: "A1" }])
    expect(result.current.entryId).toBe("entry-1")
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!)).toEqual({
      turns: [{ question: "Q1", answer: "A1" }],
      entryId: "entry-1",
    })
  })

  it("rehydrates persisted turns on a fresh mount", () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ turns: [{ question: "Q", answer: "A" }], entryId: "e1" }),
    )
    const { result } = renderHook(() => useJournalChatState(), { wrapper })
    expect(result.current.turns).toEqual([{ question: "Q", answer: "A" }])
    expect(result.current.entryId).toBe("e1")
  })

  it("reset clears turns, entryId, and storage", () => {
    const { result } = renderHook(() => useJournalChatState(), { wrapper })
    act(() => {
      result.current.addTurn({ question: "Q", answer: "A" })
      result.current.setEntryId("e1")
    })
    act(() => result.current.reset())
    expect(result.current.turns).toEqual([])
    expect(result.current.entryId).toBeNull()
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run tests/journal-chat-store.test.tsx`
Expected: FAIL — `Cannot find module '@/lib/journalChatStore'`

- [ ] **Step 3: Write the implementation**

```tsx
// apps/web/lib/journalChatStore.tsx
"use client"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

/**
 * Committed Journal brainstorm turns + the entry they're bound to. Split
 * from the in-flight job (journalChatJobStore) the same way chatStore
 * splits committed messages from chatJobStore's in-flight job — completed
 * turns live here so a job reset (after save) never re-shows them.
 */

export type JournalTurn = { question: string; answer: string }

export type JournalChatStateContextValue = {
  turns: JournalTurn[]
  entryId: string | null
  addTurn: (turn: JournalTurn) => void
  setEntryId: (id: string | null) => void
  reset: () => void
}

export const JOURNAL_CHAT_HISTORY_STORAGE_KEY = "ai-agent:journal-chat-history:v1"
const MAX_TURNS = 50

type Persisted = { turns: JournalTurn[]; entryId: string | null }

function isJournalTurn(value: unknown): value is JournalTurn {
  if (typeof value !== "object" || value === null) return false
  const t = value as Partial<JournalTurn>
  return typeof t.question === "string" && typeof t.answer === "string"
}

function capTurns(turns: JournalTurn[]): JournalTurn[] {
  if (turns.length <= MAX_TURNS) return turns
  return turns.slice(turns.length - MAX_TURNS)
}

function loadPersisted(): Persisted {
  if (typeof window === "undefined") return { turns: [], entryId: null }
  try {
    const raw = window.sessionStorage.getItem(JOURNAL_CHAT_HISTORY_STORAGE_KEY)
    if (!raw) return { turns: [], entryId: null }
    const parsed = JSON.parse(raw) as Partial<Persisted>
    const turns = Array.isArray(parsed.turns)
      ? capTurns(parsed.turns.filter(isJournalTurn))
      : []
    const entryId = typeof parsed.entryId === "string" ? parsed.entryId : null
    return { turns, entryId }
  } catch {
    return { turns: [], entryId: null }
  }
}

function persist(state: Persisted): void {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(JOURNAL_CHAT_HISTORY_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // quota / unavailable — state remains in memory for the tab
  }
}

function clearPersisted(): void {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.removeItem(JOURNAL_CHAT_HISTORY_STORAGE_KEY)
  } catch {
    // ignore
  }
}

const JournalChatStateContext = createContext<JournalChatStateContextValue | null>(null)

export function JournalChatStateProvider({ children }: { children: ReactNode }) {
  const [turns, setTurns] = useState<JournalTurn[]>([])
  const [entryId, setEntryIdState] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    const persisted = loadPersisted()
    setTurns(persisted.turns)
    setEntryIdState(persisted.entryId)
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (!hydrated) return
    if (turns.length === 0 && entryId === null) {
      clearPersisted()
    } else {
      persist({ turns, entryId })
    }
  }, [turns, entryId, hydrated])

  const addTurn = useCallback((turn: JournalTurn) => {
    setTurns((prev) => capTurns([...prev, turn]))
  }, [])

  const setEntryId = useCallback((id: string | null) => {
    setEntryIdState(id)
  }, [])

  const reset = useCallback(() => {
    setTurns([])
    setEntryIdState(null)
    clearPersisted()
  }, [])

  const value = useMemo<JournalChatStateContextValue>(
    () => ({ turns, entryId, addTurn, setEntryId, reset }),
    [turns, entryId, addTurn, setEntryId, reset],
  )

  return (
    <JournalChatStateContext.Provider value={value}>
      {children}
    </JournalChatStateContext.Provider>
  )
}

export function useJournalChatState(): JournalChatStateContextValue {
  const ctx = useContext(JournalChatStateContext)
  if (!ctx) {
    throw new Error("useJournalChatState must be used inside <JournalChatStateProvider>")
  }
  return ctx
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run tests/journal-chat-store.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/journalChatStore.tsx apps/web/tests/journal-chat-store.test.tsx
git commit -m "feat(web): add journalChatStore for committed brainstorm turns"
```

---

### Task 2: `journalChatJobStore.tsx` — in-flight job with cancel support

**Files:**
- Create: `apps/web/lib/journalChatJobStore.tsx`
- Test: `apps/web/tests/journal-chat-job-store.test.tsx`

**Interfaces:**
- Consumes: `readSseEvents` from `apps/web/lib/sse.ts` (`readSseEvents(body: ReadableStream<Uint8Array>, signal?: AbortSignal): AsyncGenerator<{type: string; data: string}>`).
- Produces: `JournalChatJobStatus = "idle" | "pending" | "running" | "done" | "failed"`; `JournalChatJobState = { jobId: string | null; status: JournalChatJobStatus; question: string; targetEntryId: string | null; imagePath: string | null; assistantContent: string; error: string | null }`; `JournalChatJobStartOpts = { question: string; imagePath?: string | null; targetEntryId: string | null }`; `JournalChatJobStateProvider`; `useJournalChatJobState(): JournalChatJobState & { startJob: (opts: JournalChatJobStartOpts) => Promise<void>; cancelJob: () => void; reset: () => void; setError: (message: string) => void }`; storage key `JOURNAL_CHAT_JOB_STORAGE_KEY`.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/tests/journal-chat-job-store.test.tsx
import { act, render, renderHook, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  JOURNAL_CHAT_JOB_STORAGE_KEY as STORAGE_KEY,
  JournalChatJobStateProvider,
  useJournalChatJobState,
} from "@/lib/journalChatJobStore"

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
    await waitFor(() => expect(screen.getByTestId("content")).toHaveTextContent("resumedtail"))
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run tests/journal-chat-job-store.test.tsx`
Expected: FAIL — `Cannot find module '@/lib/journalChatJobStore'`

- [ ] **Step 3: Write the implementation**

```tsx
// apps/web/lib/journalChatJobStore.tsx
"use client"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

import { readSseEvents } from "./sse"

/**
 * In-flight Journal brainstorm job. Mirrors chatJobStore's shape/lifecycle
 * (sessionStorage hydration while in-flight, SSE stream resume) but adds
 * cancelJob — the Journal "Stop" button needs to DELETE the backend job even
 * when clicked before the POST has returned a job_id, which chatJobStore's
 * generic start/watch factory doesn't support.
 */

export type JournalChatJobStatus = "idle" | "pending" | "running" | "done" | "failed"

export type JournalChatJobState = {
  jobId: string | null
  status: JournalChatJobStatus
  question: string
  /** entryId snapshot taken at job start — later journalChatStore.entryId changes don't retarget an in-flight save. */
  targetEntryId: string | null
  imagePath: string | null
  /** Accumulating assistant content. Rebuilt from the GET stream's replay on resume, not persisted. */
  assistantContent: string
  error: string | null
}

export type JournalChatJobStartOpts = {
  question: string
  imagePath?: string | null
  targetEntryId: string | null
}

export type JournalChatJobContextValue = JournalChatJobState & {
  startJob: (opts: JournalChatJobStartOpts) => Promise<void>
  cancelJob: () => void
  reset: () => void
  setError: (message: string) => void
}

export const JOURNAL_CHAT_JOB_STORAGE_KEY = "ai-agent:journal-chat-job:v1"

const initialState: JournalChatJobState = {
  jobId: null,
  status: "idle",
  question: "",
  targetEntryId: null,
  imagePath: null,
  assistantContent: "",
  error: null,
}

const isInFlightStatus = (s: JournalChatJobStatus) => s === "pending" || s === "running"

function loadPersisted(): JournalChatJobState {
  if (typeof window === "undefined") return initialState
  try {
    const raw = window.sessionStorage.getItem(JOURNAL_CHAT_JOB_STORAGE_KEY)
    if (!raw) return initialState
    const parsed = JSON.parse(raw) as Partial<JournalChatJobState>
    const next = { ...initialState, ...parsed }
    if (isInFlightStatus(next.status) && !next.jobId) return initialState
    return next
  } catch {
    return initialState
  }
}

function persist(state: JournalChatJobState): void {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(
      JOURNAL_CHAT_JOB_STORAGE_KEY,
      JSON.stringify({ ...state, assistantContent: "" }),
    )
  } catch {
    // quota / unavailable — state remains in memory for the tab
  }
}

function clearPersisted(): void {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.removeItem(JOURNAL_CHAT_JOB_STORAGE_KEY)
  } catch {
    // ignore
  }
}

const JournalChatJobContext = createContext<JournalChatJobContextValue | null>(null)

export function JournalChatJobStateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<JournalChatJobState>(initialState)
  const [hydrated, setHydrated] = useState(false)
  // Set when Stop is clicked before the POST has returned a job_id — startJob
  // checks this right after the id arrives and DELETEs immediately instead
  // of ever entering "running".
  const cancelRequested = useRef(false)

  useEffect(() => {
    setState(loadPersisted())
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (!hydrated) return
    if (state.jobId && isInFlightStatus(state.status)) {
      persist(state)
    } else {
      clearPersisted()
    }
  }, [state, hydrated])

  const jobId = state.jobId
  const inFlight = isInFlightStatus(state.status)

  useEffect(() => {
    if (!hydrated || !jobId || !inFlight) return
    const controller = new AbortController()
    let stopped = false

    const boundSetState = (mapper: (prev: JournalChatJobState) => JournalChatJobState) => {
      if (stopped) return
      setState((prev) => (prev.jobId !== jobId ? prev : mapper(prev)))
    }

    void (async () => {
      boundSetState((prev) => ({ ...prev, assistantContent: "" }))
      let res: Response
      try {
        res = await fetch(`/api/chat/${jobId}/stream`, {
          method: "GET",
          cache: "no-store",
          signal: controller.signal,
        })
      } catch (e) {
        if (controller.signal.aborted) return
        boundSetState((prev) => ({
          ...prev,
          status: "failed",
          error: e instanceof Error ? e.message : "Network error",
        }))
        return
      }
      if (controller.signal.aborted) return
      if (res.status === 404) {
        boundSetState(() => ({
          ...initialState,
          status: "failed",
          error: "The previous brainstorm job is no longer available — please ask again.",
        }))
        return
      }
      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => "")
        boundSetState((prev) => ({
          ...prev,
          status: "failed",
          error: `Stream failed (HTTP ${res.status}): ${text}`,
        }))
        return
      }
      let answer = ""
      try {
        for await (const ev of readSseEvents(res.body, controller.signal)) {
          if (ev.type !== "message" || !ev.data) continue
          answer = answer ? `${answer}\n${ev.data}` : ev.data
          boundSetState((prev) => ({
            ...prev,
            assistantContent: prev.assistantContent
              ? `${prev.assistantContent}\n${ev.data}`
              : ev.data,
          }))
        }
      } catch (e) {
        if (controller.signal.aborted) return
        boundSetState((prev) => ({
          ...prev,
          status: "failed",
          error: e instanceof Error ? e.message : "Stream read error",
        }))
        return
      }
      if (controller.signal.aborted) return
      if (!answer) {
        boundSetState((prev) => ({
          ...prev,
          status: "failed",
          error: "Brainstorm returned an empty answer.",
        }))
        return
      }
      boundSetState((prev) => ({ ...prev, status: "done" }))
    })()

    return () => {
      stopped = true
      controller.abort()
    }
  }, [hydrated, jobId, inFlight])

  const startJob = useCallback(async (opts: JournalChatJobStartOpts) => {
    cancelRequested.current = false
    setState(() => ({
      ...initialState,
      status: "pending",
      question: opts.question,
      targetEntryId: opts.targetEntryId,
      imagePath: opts.imagePath ?? null,
    }))
    let post: Response
    try {
      post = await fetch("/api/journal/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question: opts.question,
          ...(opts.imagePath ? { image_path: opts.imagePath } : {}),
        }),
      })
    } catch (e) {
      setState((prev) => ({
        ...prev,
        status: "failed",
        error: e instanceof Error ? e.message : "Network error",
      }))
      return
    }
    if (!post.ok) {
      const text = await post.text().catch(() => "")
      const message =
        post.status === 404
          ? "No journal entries yet — record something first."
          : `Brainstorm failed (HTTP ${post.status}): ${text}`
      setState((prev) => ({ ...prev, status: "failed", error: message }))
      return
    }
    const body = (await post.json()) as { job_id?: string }
    if (!body.job_id) {
      setState((prev) => ({
        ...prev,
        status: "failed",
        error: "POST /api/journal/chat returned no job_id",
      }))
      return
    }
    if (cancelRequested.current) {
      void fetch(`/api/chat/${body.job_id}`, { method: "DELETE", cache: "no-store" })
      cancelRequested.current = false
      setState(() => initialState)
      return
    }
    setState((prev) =>
      prev.status === "pending" ? { ...prev, jobId: body.job_id ?? null, status: "running" } : prev,
    )
  }, [])

  const cancelJob = useCallback(() => {
    if (state.jobId) {
      void fetch(`/api/chat/${state.jobId}`, { method: "DELETE", cache: "no-store" })
      setState(initialState)
    } else {
      cancelRequested.current = true
    }
  }, [state.jobId])

  const reset = useCallback(() => {
    setState(initialState)
    clearPersisted()
  }, [])

  const setError = useCallback((message: string) => {
    setState((prev) => ({ ...prev, status: "failed", error: message }))
  }, [])

  const value = useMemo<JournalChatJobContextValue>(
    () => ({ ...state, startJob, cancelJob, reset, setError }),
    [state, startJob, cancelJob, reset, setError],
  )

  return (
    <JournalChatJobContext.Provider value={value}>{children}</JournalChatJobContext.Provider>
  )
}

export function useJournalChatJobState(): JournalChatJobContextValue {
  const ctx = useContext(JournalChatJobContext)
  if (!ctx) {
    throw new Error("useJournalChatJobState must be used inside <JournalChatJobStateProvider>")
  }
  return ctx
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run tests/journal-chat-job-store.test.tsx`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/journalChatJobStore.tsx apps/web/tests/journal-chat-job-store.test.tsx
git commit -m "feat(web): add journalChatJobStore for in-flight brainstorm jobs"
```

---

### Task 3: `JournalChatBridge` — save-on-completion, mounted at layout level

**Files:**
- Create: `apps/web/components/journal/JournalChatBridge.tsx`
- Test: `apps/web/tests/journal-chat-bridge.test.tsx`

**Interfaces:**
- Consumes: `useJournalChatJobState()` (Task 2), `useJournalChatState()` (Task 1), `formatQaBlock(question: string, answer: string): string` from `apps/web/lib/journalQa.ts`.
- Produces: `JournalChatBridge(): null` — no props, renders nothing, must be mounted inside both providers.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/tests/journal-chat-bridge.test.tsx
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
      fetchMock.mock.calls.filter(([u]) => String(u) === "/api/journal" || String(u).startsWith("/api/journal/")).length,
    ).toBe(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run tests/journal-chat-bridge.test.tsx`
Expected: FAIL — `Cannot find module '@/components/journal/JournalChatBridge'`

- [ ] **Step 3: Write the implementation**

```tsx
// apps/web/components/journal/JournalChatBridge.tsx
"use client"
import { useEffect, useRef } from "react"

import { formatQaBlock } from "@/lib/journalQa"
import { useJournalChatJobState } from "@/lib/journalChatJobStore"
import { useJournalChatState } from "@/lib/journalChatStore"

/**
 * Always-mounted glue between the Journal brainstorm job and its committed
 * turn history. Runs at the (main) layout level (not inside JournalScreen)
 * so a finished job is saved and committed even while the user has
 * navigated to another page. Renders nothing.
 */
export function JournalChatBridge(): null {
  const job = useJournalChatJobState()
  const journalChat = useJournalChatState()
  // Guards against the completion effect re-running for the same job (e.g.
  // a StrictMode double-invoke or an unrelated re-render while the async
  // save is in flight) — without this a slow save could fire twice.
  const processing = useRef<string | null>(null)

  useEffect(() => {
    if (job.status !== "done" || !job.jobId) return
    if (processing.current === job.jobId) return
    processing.current = job.jobId

    const { question, assistantContent, targetEntryId } = job

    void (async () => {
      const qaBlock = formatQaBlock(question, assistantContent)
      let saveRes: Response
      try {
        saveRes = targetEntryId
          ? await fetch(`/api/journal/${targetEntryId}`, {
              method: "PATCH",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ content: qaBlock }),
            })
          : await fetch("/api/journal", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ content: qaBlock, item: question.slice(0, 20) }),
            })
      } catch (e) {
        job.setError(e instanceof Error ? e.message : "Auto-save network error")
        processing.current = null
        return
      }
      if (!saveRes.ok) {
        const body = await saveRes.text().catch(() => "")
        job.setError(`Auto-save failed (HTTP ${saveRes.status}): ${body}`)
        processing.current = null
        return
      }
      let entryId = targetEntryId
      if (!entryId) {
        const saved = (await saveRes.json()) as { id: string }
        entryId = saved.id
      }
      journalChat.addTurn({ question, answer: assistantContent })
      journalChat.setEntryId(entryId)
      job.reset()
      processing.current = null
    })()
  }, [job, journalChat])

  return null
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run tests/journal-chat-bridge.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/journal/JournalChatBridge.tsx apps/web/tests/journal-chat-bridge.test.tsx
git commit -m "feat(web): add JournalChatBridge to save+commit brainstorm jobs on completion"
```

---

### Task 4: Wire providers + bridge into `(main)/layout.tsx`

**Files:**
- Modify: `apps/web/app/(main)/layout.tsx`

**Interfaces:**
- Consumes: `JournalChatStateProvider` (Task 1), `JournalChatJobStateProvider` (Task 2), `JournalChatBridge` (Task 3).

- [ ] **Step 1: Edit the layout**

Replace the full file content:

```tsx
// apps/web/app/(main)/layout.tsx
import { redirect } from "next/navigation"

import { apiFetch } from "@/lib/api"
import { Sidebar } from "@/components/Sidebar"
import { ServiceTabs } from "@/components/ServiceTabs"
import { JournalChatBridge } from "@/components/journal/JournalChatBridge"
import { ChatJobStateProvider } from "@/lib/chatJobStore"
import { ChatStateProvider } from "@/lib/chatStore"
import { JobStateProvider } from "@/lib/jobStore"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"

async function isOnboarded(): Promise<boolean> {
  try {
    const res = await apiFetch("/api/state")
    if (!res.ok) return false
    const data = (await res.json()) as { onboarded?: boolean }
    return Boolean(data.onboarded)
  } catch {
    return false
  }
}

export const dynamic = "force-dynamic"

export default async function MainLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Guard: kick anyone not onboarded back to / for the wizard.
  if (!(await isOnboarded())) redirect("/")
  return (
    <JobStateProvider>
      <ChatStateProvider>
        <ChatJobStateProvider>
          <JournalChatStateProvider>
            <JournalChatJobStateProvider>
              <JournalChatBridge />
              <div className="flex h-dvh overflow-hidden">
                <Sidebar />
                <main className="flex flex-1 flex-col overflow-hidden">
                  <ServiceTabs />
                  <div className="flex-1 overflow-y-auto p-8">{children}</div>
                </main>
              </div>
            </JournalChatJobStateProvider>
          </JournalChatStateProvider>
        </ChatJobStateProvider>
      </ChatStateProvider>
    </JobStateProvider>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd apps/web && npx tsc --noEmit`
Expected: no new errors (JournalScreen.tsx still uses local state at this point — Task 5 fixes that; if `tsc` fails only on `JournalScreen.tsx`'s pre-existing code, proceed, Task 5 resolves it).

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/\(main\)/layout.tsx
git commit -m "feat(web): mount Journal chat providers and bridge at layout level"
```

---

### Task 5: Refactor `JournalScreen.tsx` to consume the new stores

**Files:**
- Modify: `apps/web/components/screens/JournalScreen.tsx`
- Modify: `apps/web/tests/journal-cancel.test.tsx`

**Interfaces:**
- Consumes: `useJournalChatState()` (Task 1), `useJournalChatJobState()` (Task 2).

- [ ] **Step 1: Update imports**

In `apps/web/components/screens/JournalScreen.tsx`, replace:

```tsx
import { formatQaBlock } from "@/lib/journalQa"
import { readSseEvents } from "@/lib/sse"
import { useResizable } from "@/lib/hooks/useResizable"
```

with:

```tsx
import { useJournalChatJobState } from "@/lib/journalChatJobStore"
import { useJournalChatState } from "@/lib/journalChatStore"
import { useResizable } from "@/lib/hooks/useResizable"
```

Remove the now-unused local type declaration:

```tsx
type Turn = { question: string; answer: string }
```

(delete this line — the turn shape now comes from `journalChatStore`, and JournalScreen never needs to name the type explicitly since it only spreads/reads arrays of it).

- [ ] **Step 2: Replace local chat state with the stores**

Replace:

```tsx
  const [question, setQuestion] = useState("")
  const [turns, setTurns] = useState<Turn[]>([])
  const [brainstorming, setBrainstorming] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  // Tracks the journal entry id for the current brainstorm session so that
  // subsequent turns append to the same entry instead of creating new ones.
  const brainstormEntryId = useRef<string | null>(null)
  // Abort handle + backend job id for the in-flight brainstorm, so the user
  // can cancel an accidentally sent question before the answer lands.
  const brainstormAbort = useRef<{ controller: AbortController; jobId: string | null } | null>(null)
```

with:

```tsx
  const [question, setQuestion] = useState("")
  const journalChat = useJournalChatState()
  const job = useJournalChatJobState()
  const brainstorming = job.status === "pending" || job.status === "running"
  const chatError = job.error
  // Bumped on every entry switch/compose/trash toggle so a pending job
  // started under a previous view doesn't reappear if the id-matching
  // heuristic below can't distinguish "same view" from "new view" (e.g. two
  // successive new-entry sessions both have targetEntryId=null). Reset to 0
  // on every JournalScreen mount, which is exactly the state a fresh
  // navigation back to Journal starts from — so a job started before
  // navigating away still shows on return.
  const viewEpoch = useRef(0)
  const brainstormEpoch = useRef(0)
```

- [ ] **Step 3: Replace `appendToLastAnswer` + `brainstorm` + `cancelBrainstorm`**

Delete the `appendToLastAnswer` callback entirely:

```tsx
  const appendToLastAnswer = useCallback((chunk: string) => {
    setTurns((prev) => {
      if (prev.length === 0) return prev
      const last = prev[prev.length - 1]
      const answer = last.answer ? `${last.answer}\n${chunk}` : chunk
      return [...prev.slice(0, -1), { ...last, answer }]
    })
  }, [])
```

Replace the entire `brainstorm` callback (from `const brainstorm = useCallback(async () => {` through its closing `}, [question, brainstorming, brainstormImage, appendToLastAnswer, loadDates])`) with:

```tsx
  const brainstorm = useCallback(async () => {
    const q = question.trim()
    if (!q || brainstorming) return
    setQuestion("")
    brainstormEpoch.current = viewEpoch.current
    await job.startJob({
      question: q,
      imagePath: brainstormImage?.path ?? null,
      targetEntryId: journalChat.entryId,
    })
    // Cleared unconditionally (including on cancel/failure) — simpler than
    // threading the outcome back through startJob's return value, and
    // re-attaching an image to a retyped question is a minor inconvenience
    // compared to the state this replaces.
    setBrainstormImage(null)
  }, [question, brainstorming, brainstormImage, job, journalChat.entryId])
```

Replace the entire `cancelBrainstorm` callback with:

```tsx
  // Abort the in-flight brainstorm and terminate the backend job — works
  // whether or not the backend job_id has arrived yet (journalChatJobStore
  // queues the cancel and fires the DELETE once it does).
  const cancelBrainstorm = useCallback(() => {
    if (job.status === "idle") return
    const q = job.question
    job.cancelJob()
    setQuestion(q)
  }, [job])
```

- [ ] **Step 4: Update `closePanel`, `startCompose`, `loadEntry`, `toggleTrash`**

Replace:

```tsx
  const closePanel = () => {
    setSelected(null)
    setComposing(false)
    setTrashPreview(null)
    brainstormEntryId.current = null
  }

  const startCompose = () => {
    setSelected(null)
    setTrashPreview(null)
    brainstormEntryId.current = null
    setTurns([])
    setComposing(true)
  }
```

with:

```tsx
  const closePanel = () => {
    setSelected(null)
    setComposing(false)
    setTrashPreview(null)
    journalChat.setEntryId(null)
  }

  const startCompose = () => {
    setSelected(null)
    setTrashPreview(null)
    viewEpoch.current += 1
    journalChat.reset()
    setComposing(true)
  }
```

In `loadEntry`, replace:

```tsx
    setSelected(entryId)
    setComposing(false)
    // Bind the brainstorm session to this entry so subsequent turns append here.
    brainstormEntryId.current = entryId
    setTurns([])
```

with:

```tsx
    setSelected(entryId)
    setComposing(false)
    viewEpoch.current += 1
    // Bind the brainstorm session to this entry so subsequent turns append here.
    journalChat.reset()
    journalChat.setEntryId(entryId)
```

and update `loadEntry`'s dependency array from `[]` to `[journalChat]`.

In `toggleTrash`, replace:

```tsx
    setSelected(null)
    setComposing(false)
    setTrashPreview(null)
    brainstormEntryId.current = null
    setTurns([])
    if (next) void loadTrash()
  }, [showTrash, loadTrash])
```

with:

```tsx
    setSelected(null)
    setComposing(false)
    setTrashPreview(null)
    viewEpoch.current += 1
    journalChat.reset()
    if (next) void loadTrash()
  }, [showTrash, loadTrash, journalChat])
```

- [ ] **Step 5: Compute the displayed transcript and use it in the JSX**

Just before `const sortedEntries = ...`, add:

```tsx
  // The in-flight job only renders as a pending bubble while the view it
  // was started from is still current — matches the pre-refactor behavior
  // where switching entries/composing/trash cleared the visible transcript
  // even though the backend job kept running in the background.
  const showPendingTurn = job.jobId !== null && brainstormEpoch.current === viewEpoch.current
  const displayTurns = showPendingTurn
    ? [...journalChat.turns, { question: job.question, answer: job.assistantContent }]
    : journalChat.turns
```

In the JSX, replace:

```tsx
                {turns.length > 0 && (
                  <div className="flex flex-col gap-4">
                    {turns.map((turn, i) => (
```

with:

```tsx
                {displayTurns.length > 0 && (
                  <div className="flex flex-col gap-4">
                    {displayTurns.map((turn, i) => (
```

- [ ] **Step 6: Typecheck and run the existing cancel tests (expected to fail — fixed in Step 7)**

Run: `cd apps/web && npx tsc --noEmit`
Expected: PASS (no type errors)

Run: `cd apps/web && npx vitest run tests/journal-cancel.test.tsx`
Expected: FAIL — `useJournalChatState must be used inside <JournalChatStateProvider>` (JournalScreen is rendered bare in this test file)

- [ ] **Step 7: Update `journal-cancel.test.tsx` to wrap `JournalScreen` in the new providers**

At the top of `apps/web/tests/journal-cancel.test.tsx`, add imports:

```tsx
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"
```

Add a helper right after the existing `jsonResponse` helper:

```tsx
function renderJournalScreen() {
  return render(
    <JournalChatStateProvider>
      <JournalChatJobStateProvider>
        <JournalScreen />
      </JournalChatJobStateProvider>
    </JournalChatStateProvider>,
  )
}
```

Replace all three occurrences of `render(<JournalScreen />)` with `renderJournalScreen()`.

Add `window.sessionStorage.clear()` to the existing `beforeEach`/`afterEach` blocks so no state leaks between tests:

```tsx
  beforeEach(() => {
    window.sessionStorage.clear()
    vi.stubGlobal("fetch", fetchMock)
    ...
```

```tsx
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    window.sessionStorage.clear()
  })
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd apps/web && npx vitest run tests/journal-cancel.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
git add apps/web/components/screens/JournalScreen.tsx apps/web/tests/journal-cancel.test.tsx
git commit -m "refactor(web): move Journal brainstorm chat state into journalChatStore/journalChatJobStore"
```

---

### Task 6: Regression test — chat survives `JournalScreen` unmount/remount

**Files:**
- Create: `apps/web/tests/journal-chat-persist.test.tsx`

**Interfaces:**
- Consumes: `JournalScreen`, `JournalChatStateProvider`, `JournalChatJobStateProvider`, `JournalChatBridge`.

- [ ] **Step 1: Write the test**

```tsx
// apps/web/tests/journal-chat-persist.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { JournalScreen } from "@/components/screens/JournalScreen"
import { JournalChatBridge } from "@/components/journal/JournalChatBridge"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"

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

// Renders the same provider tree app/(main)/layout.tsx does, so unmounting
// just <JournalScreen /> (simulating navigating to another page) leaves the
// job/bridge running, exactly like the real layout.
function Shell({ showJournal }: { showJournal: boolean }) {
  return (
    <JournalChatStateProvider>
      <JournalChatJobStateProvider>
        <JournalChatBridge />
        {showJournal && <JournalScreen />}
      </JournalChatJobStateProvider>
    </JournalChatStateProvider>
  )
}

describe("Journal chat survives navigation away and back", () => {
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
      throw new Error(`Unmocked fetch in journal-chat-persist test: ${u}`)
    })
    vi.stubGlobal("fetch", fetchMock)
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.sessionStorage.clear()
  })

  it("shows the completed answer after unmount/remount, without duplicating the turn", async () => {
    on("/api/journal", () => jsonResponse({ entries: [] }))
    on("/api/journal/chat", () => jsonResponse({ job_id: "job-1" }, 202))
    let releaseStream: (() => void) | null = null
    const gate = new Promise<void>((resolve) => { releaseStream = resolve })
    on("/api/chat/job-1/stream", async () => {
      await gate
      return sseStream([{ data: "final answer" }])
    })
    on("/api/journal", () => jsonResponse({ id: "new-entry" }))

    const { rerender } = render(<Shell showJournal={true} />)
    fireEvent.click(screen.getByRole("button", { name: /new/i }))
    const textarea = screen.getByPlaceholderText(/what should i focus on/i)
    fireEvent.change(textarea, { target: { value: "what should I do" } })
    fireEvent.click(screen.getByRole("button", { name: "Brainstorm" }))

    await screen.findByText("Thinking…")

    // Navigate away: unmount JournalScreen but keep the providers/bridge
    // mounted, exactly like moving to another route under (main)/layout.tsx.
    rerender(<Shell showJournal={false} />)

    // Let the stream resolve while JournalScreen is unmounted.
    releaseStream!()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/journal",
      expect.objectContaining({ method: "POST" }),
    ))

    // Navigate back.
    rerender(<Shell showJournal={true} />)
    fireEvent.click(screen.getByRole("button", { name: /new/i }))

    await waitFor(() => {
      expect(screen.getByText("what should I do")).toBeInTheDocument()
      expect(screen.getByText("final answer")).toBeInTheDocument()
    })
    expect(screen.queryByText("Thinking…")).toBeNull()
    // Exactly one save call, not one per remount.
    const saveCalls = fetchMock.mock.calls.filter(
      ([u, init]) => String(u) === "/api/journal" && (init as RequestInit | undefined)?.method === "POST",
    )
    expect(saveCalls).toHaveLength(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails first (sanity check against a stale mental model)**

Run: `cd apps/web && npx vitest run tests/journal-chat-persist.test.tsx`
Expected: PASS immediately (Tasks 1–5 already implement the behavior this test exercises) — if it fails, treat the failure output as a real bug report and fix the implementation from Tasks 1–5 rather than adjusting the test to match, unless the assertion itself is wrong.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/journal-chat-persist.test.tsx
git commit -m "test(web): verify Journal chat survives JournalScreen unmount/remount"
```

---

### Task 7: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full web test suite**

Run: `cd apps/web && npx vitest run`
Expected: all tests PASS, including `journal-cancel.test.tsx`, `journal-chat-store.test.tsx`, `journal-chat-job-store.test.tsx`, `journal-chat-bridge.test.tsx`, `journal-chat-persist.test.tsx`, `chat-job-store.test.tsx`, `sse.test.ts`.

- [ ] **Step 2: Typecheck and lint**

Run: `cd apps/web && npx tsc --noEmit && npx eslint . --max-warnings 0`
Expected: no errors.

- [ ] **Step 3: Manual smoke test**

Run: `cd apps/web && npm run dev`, open the Journal page, click New, ask a brainstorm question, navigate to another tab (e.g. Portfolio) while it says "Thinking…", then navigate back to Journal and confirm the question + completed answer are visible without duplication.

- [ ] **Step 4: Update the design spec status (optional housekeeping)**

No code change — if any deviations from `docs/superpowers/specs/2026-07-08-journal-chat-persist-design.md` were made during implementation, note them in a follow-up commit message when merging.
