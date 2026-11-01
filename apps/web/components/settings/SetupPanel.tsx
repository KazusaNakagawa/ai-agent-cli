"use client"
import { useState } from "react"

import { Button } from "@/components/ui/button"

// Clears the onboarded flag so "/" shows the wizard again, then opens it in
// re-run mode (prefilled, keeps unedited config, can be cancelled).
export function SetupPanel() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const rerun = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch("/api/state", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ onboarded: false }),
      })
      if (!res.ok) {
        setError(`PUT /api/state failed (HTTP ${res.status})`)
        setBusy(false)
        return
      }
      window.location.assign("/?rerun=1")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error")
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 text-sm">
      <p className="text-muted-foreground">
        Walk through the first-run wizard again: auth mode, portfolio,
        notifications and a dry-run check. It starts from your current
        settings, and sectors, events and conflicts are left as they are.
      </p>
      <Button onClick={() => void rerun()} disabled={busy} data-testid="rerun-setup">
        {busy ? "..." : "Re-run setup wizard"}
      </Button>
      {error && (
        <p role="alert" className="text-destructive" data-testid="rerun-setup-error">
          {error}
        </p>
      )}
    </div>
  )
}
