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
          // Blank-line events (`data:` present but empty) must pass through —
          // dropping them collapses markdown paragraph breaks.
          if (ev.type !== "message") continue
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
      // Clear immediately: waiting for the persist effect leaves a window
      // where a reload could rehydrate the cancelled job.
      clearPersisted()
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
