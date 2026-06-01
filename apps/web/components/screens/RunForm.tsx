"use client"
import { useEffect, useState } from "react"

import { SessionExpiredCard } from "@/components/SessionExpiredCard"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { LoadingDots } from "@/components/ui/loading-dots"
import { useJobState } from "@/lib/jobStore"

function fmtTs(ts: string | null | undefined): string | null {
  if (!ts) return null
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

export function RunForm() {
  const [dryRunChoice, setDryRunChoice] = useState(false)
  const {
    jobId,
    status,
    dryRun,
    startedAt,
    finishedAt,
    error,
    sessionExpired,
    isBackgrounded,
    startJob,
  } = useJobState()

  // Mirror the persisted job's dryRun into the checkbox after hydration so the
  // control reflects the restored job's mode. User toggles still flow through
  // setDryRunChoice and override the restored value.
  useEffect(() => {
    if (jobId) setDryRunChoice(Boolean(dryRun))
  }, [jobId, dryRun])

  const busy = isBackgrounded

  if (sessionExpired) {
    return <SessionExpiredCard />
  }

  const started = fmtTs(startedAt)
  const finished = fmtTs(finishedAt)

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-4 pt-6">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={dryRunChoice}
              onChange={(e) => setDryRunChoice(e.target.checked)}
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
            onClick={() => void startJob({ dryRun: dryRunChoice })}
            disabled={busy}
            data-testid="run-button"
          >
            {busy ? "Running…" : "Run briefing"}
          </Button>
        </CardContent>
      </Card>

      {jobId && (
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
              Job id: <code className="font-mono">{jobId}</code>
              {dryRun && (
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
