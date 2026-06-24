"use client"
import { useCallback, useEffect, useRef, useState } from "react"

import { AppearancePanel } from "@/components/AppearancePanel"
import { ConfigFilePanel } from "@/components/ConfigFilePanel"
import { OutputExportPanel } from "@/components/OutputExportPanel"
import { UsageDashboard } from "@/components/screens/UsageDashboard"
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

type Section = {
  key: string
  label: string
  icon: string
  render: () => React.ReactNode
}

const SECTIONS: Section[] = [
  { key: "usage", label: "Usage", icon: "📈", render: () => <UsageDashboard /> },
  { key: "appearance", label: "Appearance", icon: "🎨", render: () => <AppearancePanel /> },
  { key: "config-file", label: "Config file", icon: "📁", render: () => <ConfigFilePanel /> },
  { key: "export", label: "Export data", icon: "📦", render: () => <OutputExportPanel /> },
]

const NAV_WIDTH_KEY = "ai-agent:settings-nav-width:v1"
const NAV_MIN_WIDTH = 140
const NAV_MAX_WIDTH = 480
const NAV_DEFAULT_WIDTH = 192 // matches the previous fixed w-48

export function SettingsModal() {
  const [active, setActive] = useState<string>(SECTIONS[0].key)
  const current = SECTIONS.find((s) => s.key === active) ?? SECTIONS[0]

  const [navWidth, setNavWidth] = useState(NAV_DEFAULT_WIDTH)
  const draggingRef = useRef(false)

  // Restore the persisted nav width on mount (client-only to avoid SSR mismatch).
  useEffect(() => {
    const saved = Number(localStorage.getItem(NAV_WIDTH_KEY))
    if (saved >= NAV_MIN_WIDTH && saved <= NAV_MAX_WIDTH) setNavWidth(saved)
  }, [])

  const clamp = (w: number) => Math.min(NAV_MAX_WIDTH, Math.max(NAV_MIN_WIDTH, w))

  const onDragStart = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    draggingRef.current = true
    const startX = e.clientX
    const startWidth = navWidth

    const onMove = (ev: PointerEvent) => {
      if (!draggingRef.current) return
      setNavWidth(clamp(startWidth + (ev.clientX - startX)))
    }
    const onUp = () => {
      draggingRef.current = false
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
      setNavWidth((w) => {
        try {
          localStorage.setItem(NAV_WIDTH_KEY, String(w))
        } catch {
          // localStorage unavailable (private mode / quota); width still applies
        }
        return w
      })
    }
    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)
  }, [navWidth])

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          data-testid="config-toggle"
          data-sidebar-row
          title="Config"
          aria-label="Config"
          className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-base font-semibold transition-colors hover:bg-accent/50"
        >
          <span aria-hidden>⚙️</span>
          <span data-sidebar-label>Config</span>
        </button>
      </DialogTrigger>
      <DialogContent
        data-testid="settings-modal"
        className="flex h-[80vh] w-[80vw] max-w-[80vw] gap-0 overflow-hidden p-0"
      >
        <DialogTitle className="sr-only">Config</DialogTitle>
        {/* Left: section nav (resizable) */}
        <nav
          style={{ width: navWidth }}
          className="flex shrink-0 flex-col gap-1 border-r bg-card p-3"
        >
          <p className="px-2 pb-1 text-xs font-semibold uppercase text-muted-foreground">
            Settings
          </p>
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setActive(s.key)}
              data-testid={`settings-nav-${s.key}`}
              aria-current={active === s.key}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                active === s.key
                  ? "bg-accent font-medium text-accent-foreground"
                  : "hover:bg-accent/50",
              )}
            >
              <span aria-hidden>{s.icon}</span>
              <span>{s.label}</span>
            </button>
          ))}
        </nav>
        {/* Drag handle to resize the nav */}
        <div
          role="separator"
          aria-orientation="vertical"
          data-testid="settings-nav-resizer"
          onPointerDown={onDragStart}
          className="w-1 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-primary/50"
        />
        {/* Right: active section content */}
        <div
          data-testid="settings-content"
          className="min-w-0 flex-1 overflow-y-auto p-6"
        >
          <h2 className="mb-4 text-lg font-semibold">{current.label}</h2>
          {current.render()}
        </div>
      </DialogContent>
    </Dialog>
  )
}
