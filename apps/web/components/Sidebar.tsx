"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"

import { AppearancePanel } from "@/components/AppearancePanel"
import { ConfigFilePanel } from "@/components/ConfigFilePanel"
import { SidebarDisclosure } from "@/components/SidebarDisclosure"
import {
  SIDEBAR_COLLAPSED_ATTR,
  SIDEBAR_COLLAPSED_KEY,
} from "@/lib/sidebar"
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
  // Initialize to false so SSR and the first client render agree (avoiding
  // a hydration mismatch on data-collapsed / aria-expanded / title). The
  // visible width is already correct on first paint because CSS reacts to
  // the html attribute the pre-hydration script writes; the React state
  // catches up in the mount effect below.
  const [collapsed, setCollapsed] = useState(false)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    setCollapsed(
      document.documentElement.getAttribute(SIDEBAR_COLLAPSED_ATTR) === "true",
    )
    setHydrated(true)
  }, [])

  // Persist + mirror to the html attribute whenever the user toggles. Skip
  // the initial mount tick so we don't write back the value we just read.
  useEffect(() => {
    if (!hydrated) return
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed))
    } catch {
      // localStorage unavailable (private mode / quota); state still works
    }
    if (collapsed) {
      document.documentElement.setAttribute(SIDEBAR_COLLAPSED_ATTR, "true")
    } else {
      document.documentElement.removeAttribute(SIDEBAR_COLLAPSED_ATTR)
    }
  }, [collapsed, hydrated])

  const toggle = () => setCollapsed((prev) => !prev)

  return (
    <aside
      data-sidebar-rail
      data-testid="sidebar"
      data-collapsed={collapsed}
      className="flex flex-col gap-4 border-r bg-card p-4"
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
