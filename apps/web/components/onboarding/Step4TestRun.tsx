"use client"
import { useCallback, useEffect, useRef, useState } from "react"

import { WizardData } from "./Wizard"
import { WizardShell } from "./wizard-shell"

type Props = {
  data: WizardData
  setData: (updater: (prev: WizardData) => WizardData) => void
  onBack: () => void
  step: 1 | 2 | 3 | 4
}

type JobStatus = "idle" | "pending" | "running" | "done" | "failed"

const POLL_INTERVAL_MS = 1000
const POLL_TIMEOUT_MS = 30_000

export function Step4TestRun({ onBack, step }: Props) {
  const [status, setStatus] = useState<JobStatus>("idle")
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [completing, setCompleting] = useState(false)
  const cancelledRef = useRef(false)

  useEffect(() => () => { cancelledRef.current = true }, [])

  const finishOnboarding = useCallback(async () => {
    setCompleting(true)
    try {
      const res = await fetch("/api/state", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ onboarded: true }),
      })
      if (!res.ok) {
        setError(`PUT /api/state failed (HTTP ${res.status})`)
        setCompleting(false)
        return
      }
      // Reload so the Server Component re-evaluates and renders the
      // post-onboarding placeholder.
      window.location.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error")
      setCompleting(false)
    }
  }, [])

  const runTest = useCallback(async () => {
    setError(null)
    setStatus("pending")
    setJobId(null)
    try {
      const res = await fetch("/api/run?dry_run=true", { method: "POST" })
      if (!res.ok) {
        const text = await res.text()
        setError(`POST /api/run failed (HTTP ${res.status}): ${text}`)
        setStatus("failed")
        return
      }
      const body = (await res.json()) as { job_id: string; status: JobStatus }
      setJobId(body.job_id)
      // poll
      const startedAt = Date.now()
      while (!cancelledRef.current) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          setError("Timed out waiting for the job to finish")
          setStatus("failed")
          return
        }
        const pollRes = await fetch(`/api/run/${body.job_id}`)
        if (!pollRes.ok) {
          setError(`GET /api/run/${body.job_id} failed (HTTP ${pollRes.status})`)
          setStatus("failed")
          return
        }
        const detail = (await pollRes.json()) as {
          status: JobStatus
          error?: string | null
        }
        setStatus(detail.status)
        if (detail.status === "done") return
        if (detail.status === "failed") {
          setError(detail.error ?? "Job failed without an error message")
          return
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error")
      setStatus("failed")
    }
  }, [])

  const isDone = status === "done"
  const isFailed = status === "failed"
  const busy = status === "pending" || status === "running" || completing

  let primaryLabel: string
  let primaryHandler: () => void
  if (isDone) {
    primaryLabel = "Finish"
    primaryHandler = finishOnboarding
  } else if (busy) {
    primaryLabel = "..."
    primaryHandler = () => undefined
  } else if (isFailed) {
    primaryLabel = "Retry"
    primaryHandler = () => void runTest()
  } else {
    primaryLabel = "Run test"
    primaryHandler = () => void runTest()
  }

  return (
    <WizardShell
      step={step}
      title="Verify the pipeline"
      description="Runs /api/run?dry_run=true — credential preflight only, no Claude calls."
      busy={busy}
      error={error}
      primaryLabel={primaryLabel}
      onPrimary={primaryHandler}
      onBack={isDone || completing ? undefined : onBack}
    >
      <div className="space-y-2 text-sm">
        <p>
          <span className="font-medium">Status:</span>{" "}
          <span data-testid="job-status">{status}</span>
        </p>
        {jobId && (
          <p className="text-xs text-muted-foreground">
            Job id: <code className="font-mono">{jobId}</code>
          </p>
        )}
        {isDone && (
          <p className="text-sm">
            All good. Press <strong>Finish</strong> to complete onboarding.
          </p>
        )}
      </div>
    </WizardShell>
  )
}
