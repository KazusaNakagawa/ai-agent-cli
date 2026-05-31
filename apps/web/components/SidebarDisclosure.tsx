"use client"
import { useId, useState } from "react"

import { cn } from "@/lib/utils"

type Variant = "default" | "heading"

type Props = {
  label: string
  icon: string
  testid: string
  variant?: Variant
  defaultOpen?: boolean
  children: React.ReactNode
}

// Collapsible row used inside the sidebar. `variant="heading"` renders the
// trigger as a section header (larger, semibold) so a Config-style group can
// nest other disclosures inside it without visually flattening the hierarchy.
export function SidebarDisclosure({
  label,
  icon,
  testid,
  variant = "default",
  defaultOpen = false,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const bodyId = useId()
  const isHeading = variant === "heading"
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={bodyId}
        data-testid={testid}
        className={cn(
          "flex items-center justify-between rounded-md transition-colors hover:bg-accent/50",
          isHeading
            ? "px-2 py-2 text-base font-semibold"
            : "px-3 py-2 text-sm",
        )}
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
        <div
          id={bodyId}
          className={cn(isHeading ? "pt-1" : "px-3 pb-1 pt-1")}
        >
          {children}
        </div>
      )}
    </>
  )
}
