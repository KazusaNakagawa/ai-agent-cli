"use client"
import type { ReactNode } from "react"

import { createJobStoreProvider } from "./createJobStoreProvider"
import { parseSseChunk } from "./sse"

/**
 * Chat-flavored job-backed store. Owns the *currently in-flight* chat turn
 * (question + accumulating assistant content) so a tab switch / page reload
 * while streaming can resume via ``GET /api/chat/{job_id}/stream`` (Issue
 * #125 / #126).
 *
 * Completed turns are NOT held here — they get committed into
 * ``chatStore.messages`` once the job reaches a terminal status. Keeping the
 * two concerns split means the chat history persistence (FIFO cap, multi-tab
 * survival) stays untouched, and rehydrating an in-flight job doesn't risk
 * duplicating an already-committed turn into history.
 */

export type ChatJobStatus = "idle" | "pending" | "running" | "done" | "failed"

export type ChatJobState = {
  jobId: string | null
  status: ChatJobStatus
  /** Question the user asked. Persisted so the user message can be re-rendered after reload. */
  question: string
  /** YYYY-MM-DD briefing context (re-sent on stale_session retry). */
  date: string
  /** Accumulating assistant content. NOT persisted — rebuilt from the GET stream's replay. */
  assistantContent: string
  error: string | null
  /** UI-only: surfaced via the SessionExpiredCard. */
  sessionExpired: boolean
  /** UI-only: signal to ChatForm to retry the POST once with the same question. */
  staleSession: boolean
}

export type ChatJobStartOpts = { question: string; date: string; image_path?: string }

export type ChatJobStateContextValue = ChatJobState & {
  isBackgrounded: boolean
  startJob: (opts: ChatJobStartOpts) => Promise<void>
  reset: () => void
}

// Bumped if the persisted shape changes incompatibly. Exported so tests
// and hand-rolled debugging tools read the same key — duplicating it
// would silently break after a version bump.
export const CHAT_JOB_STORAGE_KEY = "ai-agent:chat-job:v1"

const initialState: ChatJobState = {
  jobId: null,
  status: "idle",
  question: "",
  date: "",
  assistantContent: "",
  error: null,
  sessionExpired: false,
  staleSession: false,
}

const isInFlightStatus = (s: ChatJobStatus) =>
  s === "pending" || s === "running"

const { Provider, useStore } = createJobStoreProvider<
  ChatJobState,
  ChatJobStartOpts
>({
  storageKey: CHAT_JOB_STORAGE_KEY,
  initialState,
  getJobId: (s) => s.jobId,
  isInFlight: (s) => isInFlightStatus(s.status),
  // Only persist while in flight with a real jobId — completed turns live in
  // ``chatStore.messages`` instead. Persisting a finished snapshot here would
  // resurrect it on the next mount and duplicate the turn.
  isPersistable: (s) => Boolean(s.jobId) && isInFlightStatus(s.status),
  serializeForStorage: (s) => ({
    ...s,
    // sessionExpired / staleSession / assistantContent are all transient or
    // recoverable from the backend's replay. Strip them so a reload doesn't
    // resurrect stale UI state, and so we don't have to dedupe the SSE
    // replay against a partially-built buffer.
    assistantContent: "",
    sessionExpired: false,
    staleSession: false,
  }),

  start: async ({ question, date, image_path }, { setState }) => {
    setState(() => ({
      ...initialState,
      status: "pending",
      question,
      date,
    }))
    try {
      const post = await fetch("/api/chat", {
        method: "POST",
        cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ date, question, ...(image_path ? { image_path } : {}) }),
      })
      if (post.status === 401) {
        setState(() => ({ ...initialState, sessionExpired: true }))
        return
      }
      if (!post.ok) {
        const text = await post.text().catch(() => "")
        setState((prev) => ({
          ...prev,
          status: "failed",
          error: `POST /api/chat failed (HTTP ${post.status}): ${text}`,
        }))
        return
      }
      const body = (await post.json()) as { job_id?: string }
      if (!body.job_id) {
        setState((prev) => ({
          ...prev,
          status: "failed",
          error: "POST /api/chat returned no job_id",
        }))
        return
      }
      setState((prev) => ({
        ...prev,
        jobId: body.job_id ?? null,
        status: "running",
      }))
    } catch (e) {
      setState((prev) => ({
        ...prev,
        status: "failed",
        error: e instanceof Error ? e.message : "Network error",
      }))
    }
  },

  watch: async (jobId, { signal, setState }) => {
    // The backend replays every buffered event on (re)connect, so the
    // assistant content we already have on this render could collide with the
    // replay. Reset to "" at the start and rebuild — slightly visible on
    // resume but correctness wins over a flash-free animation.
    setState((prev) => ({ ...prev, assistantContent: "" }))

    let res: Response
    try {
      res = await fetch(`/api/chat/${jobId}/stream`, {
        method: "GET",
        cache: "no-store",
        signal,
      })
    } catch (e) {
      if (signal.aborted) return
      setState((prev) => ({
        ...prev,
        status: "failed",
        error: e instanceof Error ? e.message : "Network error",
      }))
      return
    }
    if (signal.aborted) return
    if (res.status === 401) {
      setState((prev) => ({ ...prev, sessionExpired: true, status: "failed" }))
      return
    }
    if (res.status === 404) {
      // Backend no longer knows this job (process restart, eviction). Clear
      // cleanly with an informative message; ChatForm will commit nothing.
      setState(() => ({
        ...initialState,
        status: "failed",
        error:
          "The previous chat job is no longer available — please ask again.",
      }))
      return
    }
    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => "")
      setState((prev) => ({
        ...prev,
        status: "failed",
        error: `GET /api/chat/${jobId}/stream failed (HTTP ${res.status}): ${text}`,
      }))
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        if (signal.aborted) return
        buffer += decoder.decode(value, { stream: true })
        const { events, rest } = parseSseChunk(buffer)
        buffer = rest
        for (const ev of events) {
          if (signal.aborted) return
          if (ev.type === "message") {
            setState((prev) => ({
              ...prev,
              assistantContent:
                prev.assistantContent +
                (prev.assistantContent ? "\n" : "") +
                ev.data,
            }))
          } else if (ev.type === "stale_session") {
            // Backend wiped .sessions/<date>; ChatForm sees this flag on
            // terminal and re-issues the POST once with the same question.
            setState((prev) => ({ ...prev, staleSession: true }))
          } else if (ev.type === "error") {
            setState((prev) => ({
              ...prev,
              error: ev.data || "stream error",
            }))
          }
        }
      }
    } catch (e) {
      if (signal.aborted) return
      setState((prev) => ({
        ...prev,
        status: "failed",
        error: e instanceof Error ? e.message : "Stream read error",
      }))
      return
    }

    if (signal.aborted) return
    setState((prev) => ({
      ...prev,
      // ``error`` set above by an ``event: error`` frame promotes the terminal
      // status to "failed"; otherwise the stream ended cleanly.
      status: prev.error ? "failed" : "done",
    }))
  },
})

export function ChatJobStateProvider({ children }: { children: ReactNode }) {
  return <Provider>{children}</Provider>
}

export function useChatJobState(): ChatJobStateContextValue {
  return useStore()
}
