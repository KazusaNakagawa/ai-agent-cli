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

export type JobStatus = "idle" | "pending" | "running" | "done" | "failed"

export type JobState = {
  jobId: string | null
  status: JobStatus
  dryRun: boolean
  startedAt: string | null
  finishedAt: string | null
  error: string | null
  sessionExpired: boolean
}

type StartOpts = { dryRun: boolean }

export type JobStateContextValue = JobState & {
  isBackgrounded: boolean
  startJob: (opts: StartOpts) => Promise<void>
  reset: () => void
}

// Bumped if the persisted shape changes incompatibly.
const STORAGE_KEY = "ai-agent:run-job:v1"
const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 10 * 60 * 1000

const initialState: JobState = {
  jobId: null,
  status: "idle",
  dryRun: false,
  startedAt: null,
  finishedAt: null,
  error: null,
  sessionExpired: false,
}

const isInFlight = (s: JobStatus) => s === "pending" || s === "running"
const isTerminal = (s: JobStatus) => s === "done" || s === "failed"

type ApiJobDetail = {
  job_id?: string
  status: JobStatus
  dry_run?: boolean
  started_at?: string | null
  finished_at?: string | null
  error?: string | null
}

function loadPersisted(): JobState {
  if (typeof window === "undefined") return initialState
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return initialState
    const parsed = JSON.parse(raw) as Partial<JobState>
    return { ...initialState, ...parsed, sessionExpired: false }
  } catch {
    return initialState
  }
}

function persist(state: JobState) {
  if (typeof window === "undefined") return
  try {
    // sessionExpired is UI-only; never persist it
    const toStore = { ...state, sessionExpired: false }
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(toStore))
  } catch {
    // quota / unavailable — state remains in memory for the tab
  }
}

function clearPersisted() {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

const JobStateContext = createContext<JobStateContextValue | null>(null)

export function JobStateProvider({ children }: { children: ReactNode }) {
  // Render initialState on first paint so SSR and the first client render
  // agree (sessionStorage is unavailable on the server). The hydrate effect
  // below promotes state to whatever was persisted in this tab.
  const [state, setState] = useState<JobState>(initialState)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    setState(loadPersisted())
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (!hydrated) return
    if (!state.jobId && state.status === "idle" && !state.error) {
      clearPersisted()
    } else {
      persist(state)
    }
  }, [state, hydrated])

  const inFlight = isInFlight(state.status)

  // Polling loop. Runs while an in-flight job is present; aborted/cleaned up
  // on jobId change, status leaving in-flight, or unmount. Mount with a
  // persisted in-flight job resumes polling per the acceptance criteria.
  useEffect(() => {
    if (!hydrated) return
    if (!state.jobId) return
    if (!inFlight) return

    const jobId = state.jobId
    const ctl = new AbortController()
    const pollStartedAt = Date.now()
    let stopped = false

    const stop = () => {
      stopped = true
      ctl.abort()
    }

    ;(async () => {
      while (!stopped) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
        if (stopped) return
        if (Date.now() - pollStartedAt > POLL_TIMEOUT_MS) {
          setState((prev) =>
            prev.jobId === jobId
              ? {
                  ...prev,
                  status: "failed",
                  error: "Timed out waiting for the job to finish",
                }
              : prev,
          )
          return
        }
        try {
          const res = await fetch(`/api/run/${jobId}`, {
            cache: "no-store",
            signal: ctl.signal,
          })
          if (stopped) return
          if (res.status === 401) {
            setState((prev) => ({ ...prev, sessionExpired: true }))
            return
          }
          if (res.status === 404) {
            // Backend no longer knows this job (process restart, eviction).
            // Per AC: clear state cleanly with an informative message.
            setState({
              ...initialState,
              error:
                "The previous background job is no longer available — please run it again.",
            })
            return
          }
          if (!res.ok) {
            setState((prev) =>
              prev.jobId === jobId
                ? {
                    ...prev,
                    status: "failed",
                    error: `GET /api/run/${jobId} failed (HTTP ${res.status})`,
                  }
                : prev,
            )
            return
          }
          const detail = (await res.json()) as ApiJobDetail
          if (stopped) return
          setState((prev) =>
            prev.jobId === jobId
              ? {
                  ...prev,
                  status: detail.status,
                  startedAt: detail.started_at ?? prev.startedAt,
                  finishedAt: detail.finished_at ?? prev.finishedAt,
                  // dry_run is set on the POST response; preserve it across GETs that omit it
                  dryRun: detail.dry_run ?? prev.dryRun,
                  error:
                    detail.status === "failed"
                      ? detail.error ?? "Job failed without an error message"
                      : prev.error,
                }
                : prev,
          )
          if (isTerminal(detail.status)) return
        } catch (e) {
          if (stopped) return
          setState((prev) =>
            prev.jobId === jobId
              ? {
                  ...prev,
                  status: "failed",
                  error: e instanceof Error ? e.message : "Network error",
                }
              : prev,
          )
          return
        }
      }
    })()

    return stop
  }, [hydrated, state.jobId, inFlight])

  const startJob = useCallback(async ({ dryRun }: StartOpts) => {
    setState({
      ...initialState,
      status: "pending",
      dryRun,
    })
    try {
      const res = await fetch(`/api/run${dryRun ? "?dry_run=true" : ""}`, {
        method: "POST",
        cache: "no-store",
      })
      if (res.status === 401) {
        setState({ ...initialState, sessionExpired: true })
        return
      }
      if (!res.ok) {
        const text = await res.text()
        setState((prev) => ({
          ...prev,
          status: "failed",
          error: `POST /api/run failed (HTTP ${res.status}): ${text}`,
        }))
        return
      }
      const body = (await res.json()) as ApiJobDetail
      setState((prev) => ({
        ...prev,
        jobId: body.job_id ?? null,
        status: body.status,
        startedAt: body.started_at ?? prev.startedAt,
        finishedAt: body.finished_at ?? prev.finishedAt,
        dryRun: body.dry_run ?? prev.dryRun,
      }))
    } catch (e) {
      setState((prev) => ({
        ...prev,
        status: "failed",
        error: e instanceof Error ? e.message : "Network error",
      }))
    }
  }, [])

  const reset = useCallback(() => {
    setState(initialState)
    clearPersisted()
  }, [])

  const value = useMemo<JobStateContextValue>(
    () => ({
      ...state,
      isBackgrounded: inFlight,
      startJob,
      reset,
    }),
    [state, inFlight, startJob, reset],
  )

  return (
    <JobStateContext.Provider value={value}>
      {children}
    </JobStateContext.Provider>
  )
}

export function useJobState(): JobStateContextValue {
  const ctx = useContext(JobStateContext)
  if (!ctx) {
    throw new Error("useJobState must be used inside <JobStateProvider>")
  }
  return ctx
}
