"use client"
import { useCallback, useState } from "react"

import { SessionExpiredCard } from "@/components/SessionExpiredCard"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { LoadingDots } from "@/components/ui/loading-dots"
import { useAbortableMount } from "@/lib/hooks/useAbortableMount"

type JobStatus = "idle" | "pending" | "running" | "done" | "failed"

type JobDetail = {
  job_id: string
  status: JobStatus
  dry_run?: boolean
  started_at?: string | null
  finished_at?: string | null
  error?: string | null
}

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 10 * 60 * 1000 // 10 minutes — full runs can take ~5 min

function fmtTs(ts: string | null | undefined): string | null {
  if (!ts) return null
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

export function RunForm() {
  const [dryRun, setDryRun] = useState(false)
  const [status, setStatus] = useState<JobStatus>("idle")
  const [job, setJob] = useState<JobDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sessionExpired, setSessionExpired] = useState(false)

  // Cancel in-flight fetches and suppress setState if the component unmounts
  // mid-poll (e.g. user navigates away via the sidebar during a ~5-min run).
  const { mountedRef, abortRef } = useAbortableMount()

  const busy = status === "pending" || status === "running"

  const run = useCallback(async () => {
    abortRef.current?.abort()
    const ctl = new AbortController()
    abortRef.current = ctl
    const aborted = () => ctl.signal.aborted || !mountedRef.current

    setError(null)
    setSessionExpired(false)
    setJob(null)
    setStatus("pending")
    try {
      const postRes = await fetch(
        `/api/run${dryRun ? "?dry_run=true" : ""}`,
        { method: "POST", cache: "no-store", signal: ctl.signal },
      )
      if (aborted()) return
      if (postRes.status === 401) {
        setSessionExpired(true)
        setStatus("idle")
        return
      }
      if (!postRes.ok) {
        const text = await postRes.text()
        if (aborted()) return
        setError(`POST /api/run failed (HTTP ${postRes.status}): ${text}`)
        setStatus("failed")
        return
      }
      const body = (await postRes.json()) as JobDetail
      if (aborted()) return
      setJob(body)
      // Poll until terminal status or timeout. The 10-min ceiling bounds
      // the loop; unmount/navigation triggers AbortController + mountedRef
      // to stop polling and discard pending setState calls.
      const startedAt = Date.now()
      while (true) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
        if (aborted()) return
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          setError("Timed out waiting for the job to finish")
          setStatus("failed")
          return
        }
        const pollRes = await fetch(`/api/run/${body.job_id}`, {
          cache: "no-store",
          signal: ctl.signal,
        })
        if (aborted()) return
        if (pollRes.status === 401) {
          setSessionExpired(true)
          setStatus("idle")
          return
        }
        if (!pollRes.ok) {
          setError(`GET /api/run/${body.job_id} failed (HTTP ${pollRes.status})`)
          setStatus("failed")
          return
        }
        const detail = (await pollRes.json()) as JobDetail
        if (aborted()) return
        // Merge: the GET response may omit `dry_run`, which was set on the
        // POST response. Without merging the badge would flicker off.
        setJob((prev) => (prev ? { ...prev, ...detail } : detail))
        setStatus(detail.status)
        if (detail.status === "done") return
        if (detail.status === "failed") {
          setError(detail.error ?? "Job failed without an error message")
          return
        }
      }
    } catch (e) {
      if (aborted()) return
      setError(e instanceof Error ? e.message : "Network error")
      setStatus("failed")
    }
  }, [abortRef, dryRun, mountedRef])

  if (sessionExpired) {
    return <SessionExpiredCard />
  }

  const started = fmtTs(job?.started_at)
  const finished = fmtTs(job?.finished_at)

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-4 pt-6">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              disabled={busy}
              data-testid="dry-run-checkbox"
            />
            <span>
              Dry run
              <span className="ml-2 text-xs text-muted-foreground">
                Validates credentials and exits without calling Claude / Discord / Notion.
              </span>
            </span>
          </label>
          <Button
            size="lg"
            onClick={() => void run()}
            disabled={busy}
            data-testid="run-button"
          >
            {busy ? "Running…" : "Run briefing"}
          </Button>
        </CardContent>
      </Card>

      {job && (
        <Card>
          <CardContent className="space-y-2 pt-6 text-sm">
            <p className="flex items-center gap-2">
              <span className="font-medium">Status:</span>
              <span data-testid="job-status">{status}</span>
              {(status === "pending" || status === "running") && (
                <LoadingDots label="" data-testid="job-running" />
              )}
              {status === "done" && <span aria-hidden>✅</span>}
              {status === "failed" && (
                <span aria-hidden className="text-destructive">
                  ⚠️
                </span>
              )}
            </p>
            <p className="text-xs text-muted-foreground">
              Job id: <code className="font-mono">{job.job_id}</code>
              {job.dry_run && (
                <span className="ml-2 rounded bg-muted px-1 py-0.5 text-[10px]">
                  dry_run
                </span>
              )}
            </p>
            {started && (
              <p>
                <span className="font-medium">Started:</span> {started}
              </p>
            )}
            {finished && (
              <p data-testid="finished-at">
                <span className="font-medium">Finished:</span> {finished}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {error && (
        <Card>
          <CardContent
            className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
            data-testid="run-error"
            role="alert"
          >
            {error}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
