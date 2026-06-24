"use client"
import { useState } from "react"

import { Button } from "@/components/ui/button"

type Status = "idle" | "busy" | "success" | "error"

/** Parse the download filename out of a Content-Disposition header. */
function filenameFrom(header: string | null, fallback: string): string {
  const match = header?.match(/filename="?([^"]+)"?/)
  return match?.[1] ?? fallback
}

export function OutputExportPanel() {
  const [status, setStatus] = useState<Status>("idle")
  const [error, setError] = useState<string | null>(null)
  const busy = status === "busy"

  const onExport = async () => {
    setStatus("busy")
    setError(null)
    let res: Response
    try {
      res = await fetch("/api/export", { cache: "no-store" })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error")
      setStatus("error")
      return
    }
    if (!res.ok) {
      setError(`GET /api/export failed (HTTP ${res.status})`)
      setStatus("error")
      return
    }
    const blob = await res.blob()
    const name = filenameFrom(
      res.headers.get("content-disposition"),
      "output-export.zip",
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
    setStatus("success")
  }

  return (
    <div className="space-y-2" data-testid="output-export-panel">
      <p className="text-xs text-muted-foreground">
        Download all output files (briefing, journal, eval…) as a zip for backup
        or migration.
      </p>
      <Button
        size="sm"
        variant="outline"
        onClick={() => void onExport()}
        disabled={busy}
        data-testid="output-export"
      >
        {busy ? "Preparing…" : "Download output zip"}
      </Button>
      {status === "success" && (
        <p
          className="text-xs text-green-600 dark:text-green-400"
          data-testid="output-export-success"
        >
          Downloaded
        </p>
      )}
      {error && (
        <p className="text-xs text-destructive" data-testid="output-export-error">
          {error}
        </p>
      )}
    </div>
  )
}
