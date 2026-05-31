"use client"
type Status = "idle" | "saving" | "saved" | "error"

export function SaveStatus({ status }: { status: Status }) {
  if (status === "idle") return null
  if (status === "saving")
    return (
      <span className="text-sm text-muted-foreground" data-testid="save-status">
        Saving…
      </span>
    )
  if (status === "saved")
    return (
      <span className="text-sm text-green-600" data-testid="save-status">
        Saved
      </span>
    )
  return (
    <span className="text-sm text-destructive" data-testid="save-status">
      Save failed
    </span>
  )
}

export type { Status as SaveStatusValue }
