export type ServiceId = "briefing" | "journal" | "monitor" | "workspace"

export type NavItem = { href: string; label: string; icon: string }

export type Service = {
  id: ServiceId
  label: string
  icon: string
  defaultHref: string
  items: NavItem[]
}

// Single source of truth for the service model. Order matters: the first entry
// is the fallback when a route belongs to no service (Config / auth are global).
export const SERVICES: Service[] = [
  {
    id: "briefing",
    label: "Briefing",
    icon: "📚",
    defaultHref: "/portfolio",
    items: [
      { href: "/portfolio", label: "Portfolio", icon: "📊" },
      { href: "/watch-sectors", label: "Watch Sectors", icon: "🌐" },
      { href: "/geopolitical", label: "Geopolitical Risks", icon: "🗺️" },
      { href: "/run", label: "Run", icon: "▶️" },
      { href: "/chat", label: "Q&A Chat", icon: "💬" },
      { href: "/briefing", label: "Briefing", icon: "📚" },
    ],
  },
  {
    id: "journal",
    label: "Journal",
    icon: "📓",
    defaultHref: "/journal",
    items: [{ href: "/journal", label: "Journal", icon: "📓" }],
  },
  {
    id: "monitor",
    label: "Monitor",
    icon: "📈",
    defaultHref: "/monitor",
    items: [{ href: "/monitor", label: "Monitor", icon: "📈" }],
  },
  {
    id: "workspace",
    label: "Workspace",
    icon: "🗂️",
    defaultHref: "/workspace",
    items: [{ href: "/workspace", label: "Workspace", icon: "🗂️" }],
  },
]

// Derive the active service from the current route. A service owns the path if
// any of its item hrefs matches exactly or is a path-segment prefix. First
// match wins; unmatched routes fall back to the first service (briefing).
export function serviceForPath(pathname: string): Service {
  for (const service of SERVICES) {
    for (const item of service.items) {
      if (pathname === item.href || pathname.startsWith(item.href + "/")) {
        return service
      }
    }
  }
  return SERVICES[0]
}
