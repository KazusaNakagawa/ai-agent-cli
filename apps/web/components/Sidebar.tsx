"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"

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

export function Sidebar() {
  const pathname = usePathname()
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
      </section>
    </aside>
  )
}
