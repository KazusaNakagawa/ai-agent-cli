"use client"
import { useRouter } from "next/navigation"
import { useRef, useState } from "react"

import { Button } from "@/components/ui/button"

type Status = "idle" | "busy" | "success" | "error"

const DOWNLOAD_NAME = "briefing.json"

export function ConfigFilePanel() {
  const router = useRouter()
  const fileRef = useRef<HTMLInputElement>(null)
  const [status, setStatus] = useState<Status>("idle")
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const busy = status === "busy"

  const onExport = async () => {
    setStatus("busy")
    setError(null)
    setSuccessMsg(null)
    let res: Response
    try {
      res = await fetch("/api/config", { cache: "no-store" })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error")
      setStatus("error")
      return
    }
    if (!res.ok) {
      setError(`GET /api/config failed (HTTP ${res.status})`)
      setStatus("error")
      return
    }
    const data = await res.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = DOWNLOAD_NAME
    a.click()
    URL.revokeObjectURL(url)
    setSuccessMsg("Exported")
    setStatus("success")
  }

  const onImportClick = () => fileRef.current?.click()

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = "" // allow re-selecting the same file later
    if (!file) return
    setStatus("busy")
    setError(null)
    setSuccessMsg(null)

    let parsed: unknown
    try {
      const text = await file.text()
      parsed = JSON.parse(text)
    } catch {
      setError("Invalid JSON — file is not parseable")
      setStatus("error")
      return
    }

    let res: Response
    try {
      res = await fetch("/api/config", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(parsed),
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error")
      setStatus("error")
      return
    }
    if (res.ok) {
      setSuccessMsg("Imported")
      setStatus("success")
      router.refresh()
      return
    }
    if (res.status === 422) {
      setError("Schema validation failed — file does not match briefing.json")
    } else {
      setError(`PUT /api/config failed (HTTP ${res.status})`)
    }
    setStatus("error")
  }

  return (
    <div className="space-y-2" data-testid="config-file-panel">
      <div className="flex flex-col gap-1">
        <Button
          size="sm"
          variant="outline"
          onClick={() => void onExport()}
          disabled={busy}
          data-testid="config-export"
        >
          Export
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onImportClick}
          disabled={busy}
          data-testid="config-import"
        >
          Import
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(e) => void onFileChange(e)}
          data-testid="config-import-input"
        />
      </div>
      {successMsg && (
        <p
          className="text-xs text-green-600 dark:text-green-400"
          data-testid="config-success"
        >
          {successMsg}
        </p>
      )}
      {error && (
        <p className="text-xs text-destructive" data-testid="config-error">
          {error}
        </p>
      )}
    </div>
  )
}
