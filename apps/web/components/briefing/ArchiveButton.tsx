import { useState } from "react"

type Status = "idle" | "running" | "done" | "error"

/** Triggers POST /api/archive (previous month) and surfaces the result inline. */
export function ArchiveButton() {
  const [status, setStatus] = useState<Status>("idle")
  const [message, setMessage] = useState<string>("")

  const run = async () => {
    setStatus("running")
    setMessage("")
    try {
      const res = await fetch("/api/archive", { method: "POST", cache: "no-store" })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setStatus("error")
        setMessage(String(data?.detail ?? `HTTP ${res.status}`))
        return
      }
      setStatus("done")
      setMessage(String(data?.stdout ?? "").trim() || "Archive complete.")
    } catch (e) {
      setStatus("error")
      setMessage(String(e))
    }
  }

  return (
    <div className="flex items-center gap-2 px-2 py-1">
      <button
        data-testid="archive-button"
        onClick={run}
        disabled={status === "running"}
        className="rounded border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:opacity-50"
      >
        {status === "running" ? "Archiving…" : "Archive last month"}
      </button>
      {message && (
        <span
          data-testid="archive-message"
          className={status === "error" ? "text-xs text-destructive" : "text-xs text-muted-foreground"}
        >
          {message}
        </span>
      )}
    </div>
  )
}
