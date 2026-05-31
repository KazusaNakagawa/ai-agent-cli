"use client"
import { useId, useState } from "react"

type Props = {
  label: string
  icon: string
  testid: string
  children: React.ReactNode
}

// Collapsible row used inside the sidebar's Config section. Keeps each
// settings panel hidden behind a single click so the section stays compact
// as more entries are added (Appearance, Config file, ...).
export function SidebarDisclosure({ label, icon, testid, children }: Props) {
  const [open, setOpen] = useState(false)
  const bodyId = useId()
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={bodyId}
        data-testid={testid}
        className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent/50"
      >
        <span className="flex items-center gap-2">
          <span aria-hidden>{icon}</span>
          <span>{label}</span>
        </span>
        <span aria-hidden className="text-xs text-muted-foreground">
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <div id={bodyId} className="px-3 pb-1 pt-1">
          {children}
        </div>
      )}
    </>
  )
}
