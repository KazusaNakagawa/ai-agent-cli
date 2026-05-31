"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"

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

export function Sidebar() {
  const pathname = usePathname()
  // SSR + first client render both produce collapsed=false to avoid a
  // hydration mismatch; the effect below corrects the state on mount.
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    try {
      if (localStorage.getItem(COLLAPSED_KEY) === "true") setCollapsed(true)
    } catch {
      // localStorage unavailable (private mode / quota); fall back to default
    }
  }, [])

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem(COLLAPSED_KEY, String(next))
      } catch {
        // see above
      }
      return next
    })
  }

  return (
    <aside
      className={cn(
        "flex flex-col gap-4 border-r bg-card p-4 transition-[width] duration-150",
        collapsed ? "w-14" : "w-60",
      )}
      data-testid="sidebar"
      data-collapsed={collapsed}
    >
      <div
        className={cn(
          "flex items-center",
          collapsed ? "justify-center" : "justify-between",
        )}
      >
        {!collapsed && (
          <span className="px-2 text-base font-semibold">ai-agent</span>
        )}
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          data-testid="sidebar-toggle"
          className="rounded-md p-1 text-sm text-muted-foreground transition-colors hover:bg-accent/50"
        >
          <span aria-hidden>{collapsed ? "›" : "‹"}</span>
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
                title={collapsed ? item.label : undefined}
                aria-label={collapsed ? item.label : undefined}
                className={cn(
                  "flex items-center gap-2 rounded-md text-sm transition-colors",
                  collapsed ? "justify-center px-0 py-2" : "px-3 py-2",
                  active
                    ? "bg-accent font-medium text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
                data-testid={`nav-${item.href.slice(1)}`}
              >
                <span aria-hidden>{item.icon}</span>
                {!collapsed && <span>{item.label}</span>}
              </Link>
            )
          })}
        </nav>
      </section>

      {!collapsed && (
        <section className="flex flex-col gap-1">
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
      )}
    </aside>
  )
}
