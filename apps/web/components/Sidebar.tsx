"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState } from "react"

import { AppearancePanel } from "@/components/AppearancePanel"
import { cn } from "@/lib/utils"

type Item = { href: string; label: string; icon: string }

const ITEMS: Item[] = [
  { href: "/portfolio", label: "Portfolio", icon: "📊" },
  { href: "/watch-sectors", label: "Watch Sectors", icon: "🌐" },
  { href: "/geopolitical", label: "Geopolitical Risks", icon: "🗺️" },
  { href: "/credentials", label: "Credentials", icon: "📨" },
  { href: "/auth", label: "Auth", icon: "🔑" },
  { href: "/run", label: "Run", icon: "▶️" },
  { href: "/chat", label: "Q&A Chat", icon: "💬" },
]

export function Sidebar() {
  const pathname = usePathname()
  const [appearanceOpen, setAppearanceOpen] = useState(false)
  return (
    <aside className="flex w-60 flex-col gap-4 border-r bg-card p-4">
      <section className="flex flex-col gap-1">
        <h1 className="px-2 pb-2 text-base font-semibold">ai-agent</h1>
        <nav className="flex flex-col gap-1">
          {ITEMS.map((item) => {
            const active = pathname === item.href
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-accent font-medium text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
                data-testid={`nav-${item.href.slice(1)}`}
              >
                <span aria-hidden>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            )
          })}
        </nav>
      </section>

      <section className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 px-2 pb-2 text-base font-semibold">
          <span aria-hidden>⚙️</span>
          <span>Config</span>
        </h2>
        <button
          type="button"
          onClick={() => setAppearanceOpen((v) => !v)}
          aria-expanded={appearanceOpen}
          aria-controls="appearance-panel-body"
          data-testid="appearance-toggle"
          className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent/50"
        >
          <span className="flex items-center gap-2">
            <span aria-hidden>🎨</span>
            <span>Appearance</span>
          </span>
          <span aria-hidden className="text-xs text-muted-foreground">
            {appearanceOpen ? "▾" : "▸"}
          </span>
        </button>
        {appearanceOpen && (
          <div id="appearance-panel-body" className="px-3 pb-1 pt-1">
            <AppearancePanel />
          </div>
        )}
      </section>
    </aside>
  )
}
