"use client"
import type { ReactNode } from "react"

import { createJobStoreProvider } from "./createJobStoreProvider"

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

const isInFlightStatus = (s: JobStatus) => s === "pending" || s === "running"
const isTerminal = (s: JobStatus) => s === "done" || s === "failed"

type ApiJobDetail = {
  job_id?: string
  status: JobStatus
  dry_run?: boolean
  started_at?: string | null
  finished_at?: string | null
  error?: string | null
}

const { Provider, useStore } = createJobStoreProvider<JobState, StartOpts>({
  storageKey: STORAGE_KEY,
  initialState,
  getJobId: (s) => s.jobId,
  isInFlight: (s) => isInFlightStatus(s.status),
  // sessionExpired is UI-only; never persist it. Persist when there's anything
  // worth resuming: a jobId or a surfaced error message.
  isPersistable: (s) => Boolean(s.jobId) || Boolean(s.error),
  serializeForStorage: (s) => ({ ...s, sessionExpired: false }),

  start: async ({ dryRun }, { setState }) => {
    setState(() => ({ ...initialState, status: "pending", dryRun }))
    try {
      const res = await fetch(`/api/run${dryRun ? "?dry_run=true" : ""}`, {
        method: "POST",
        cache: "no-store",
      })
      if (res.status === 401) {
        setState(() => ({ ...initialState, sessionExpired: true }))
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
  },

  watch: async (jobId, { signal, setState }) => {
    const pollStartedAt = Date.now()
    while (!signal.aborted) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
      if (signal.aborted) return
      if (Date.now() - pollStartedAt > POLL_TIMEOUT_MS) {
        setState((prev) => ({
          ...prev,
          status: "failed",
          error: "Timed out waiting for the job to finish",
        }))
        return
      }
      try {
        const res = await fetch(`/api/run/${jobId}`, {
          cache: "no-store",
          signal,
        })
        if (signal.aborted) return
        if (res.status === 401) {
          setState((prev) => ({ ...prev, sessionExpired: true }))
          return
        }
        if (res.status === 404) {
          // Backend no longer knows this job (process restart, eviction).
          // Per AC: clear state cleanly with an informative message.
          setState(() => ({
            ...initialState,
            error:
              "The previous background job is no longer available — please run it again.",
          }))
          return
        }
        if (!res.ok) {
          setState((prev) => ({
            ...prev,
            status: "failed",
            error: `GET /api/run/${jobId} failed (HTTP ${res.status})`,
          }))
          return
        }
        const detail = (await res.json()) as ApiJobDetail
        if (signal.aborted) return
        setState((prev) => ({
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
        }))
        if (isTerminal(detail.status)) return
      } catch (e) {
        if (signal.aborted) return
        setState((prev) => ({
          ...prev,
          status: "failed",
          error: e instanceof Error ? e.message : "Network error",
        }))
        return
      }
    }
  },
})

export function JobStateProvider({ children }: { children: ReactNode }) {
  return <Provider>{children}</Provider>
}

export function useJobState(): JobStateContextValue {
  return useStore()
}
