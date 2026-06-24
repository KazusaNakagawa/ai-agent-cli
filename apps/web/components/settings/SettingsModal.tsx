"use client"
import { useState } from "react"

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

export function SettingsModal() {
  const [active, setActive] = useState<string>(SECTIONS[0].key)
  const current = SECTIONS.find((s) => s.key === active) ?? SECTIONS[0]

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
        className="flex h-[80vh] max-w-3xl gap-0 overflow-hidden p-0"
      >
        <DialogTitle className="sr-only">Config</DialogTitle>
        {/* Left: section nav */}
        <nav className="flex w-48 shrink-0 flex-col gap-1 border-r bg-card p-3">
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
