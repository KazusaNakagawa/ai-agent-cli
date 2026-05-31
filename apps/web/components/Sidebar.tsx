"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState } from "react"

import { AppearancePanel } from "@/components/AppearancePanel"
import { ConfigFilePanel } from "@/components/ConfigFilePanel"
import { SidebarDisclosure } from "@/components/SidebarDisclosure"
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

const COLLAPSED_KEY = "ai-agent:sidebar-collapsed"
const HTML_ATTR = "data-sidebar-collapsed"

// Read the collapsed flag already painted onto <html> by the pre-hydration
// script (see app/layout.tsx via themeBootScript). On the server the flag
// can't exist yet; React's first client render reads the same DOM the
// pre-hydration script just wrote, so the initial paint already matches the
// final state — no expanded→collapsed flash on reload.
function readInitialCollapsed(): boolean {
  if (typeof document === "undefined") return false
  return document.documentElement.getAttribute(HTML_ATTR) === "true"
}

export function Sidebar() {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState(readInitialCollapsed)

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem(COLLAPSED_KEY, String(next))
      } catch {
        // localStorage unavailable (private mode / quota); toggle still works
      }
      if (next) {
        document.documentElement.setAttribute(HTML_ATTR, "true")
      } else {
        document.documentElement.removeAttribute(HTML_ATTR)
      }
      return next
    })
  }

  return (
    <aside
      data-sidebar-rail
      data-testid="sidebar"
      data-collapsed={collapsed}
      className="flex flex-col gap-4 border-r bg-card p-4 transition-[width] duration-150"
    >
      <div data-sidebar-header className="flex items-center justify-between">
        <span data-sidebar-brand className="px-2 text-base font-semibold">
          ai-agent
        </span>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          data-testid="sidebar-toggle"
          className="rounded-md p-1 text-sm text-muted-foreground transition-colors hover:bg-accent/50"
        >
          <span aria-hidden data-sidebar-toggle-icon />
        </button>
      </div>

      <section className="flex flex-col gap-1">
        <nav className="flex flex-col gap-1">
          {ITEMS.map((item) => {
            const active = pathname === item.href
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                aria-label={item.label}
                data-sidebar-row
                data-testid={`nav-${item.href.slice(1)}`}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-accent font-medium text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
              >
                <span aria-hidden>{item.icon}</span>
                <span data-sidebar-label>{item.label}</span>
              </Link>
            )
          })}
        </nav>
      </section>

      <section
        data-sidebar-section="config"
        className="flex flex-col gap-1"
      >
        <SidebarDisclosure
          label="Config"
          icon="⚙️"
          testid="config-toggle"
          variant="heading"
        >
          <div className="flex flex-col gap-1">
            <SidebarDisclosure
              label="Appearance"
              icon="🎨"
              testid="appearance-toggle"
            >
              <AppearancePanel />
            </SidebarDisclosure>
            <SidebarDisclosure
              label="Config file"
              icon="📁"
              testid="config-file-toggle"
            >
              <ConfigFilePanel />
            </SidebarDisclosure>
          </div>
        </SidebarDisclosure>
      </section>
    </aside>
  )
}
