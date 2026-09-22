import {
  Activity,
  BookOpen,
  ChartPie,
  FolderTree,
  Globe,
  Map,
  MessageSquare,
  NotebookPen,
  Play,
  type LucideIcon,
} from "lucide-react"

export type ServiceId = "briefing" | "journal" | "monitor" | "workspace"

export type NavItem = { href: string; label: string; icon: LucideIcon }

export type Service = {
  id: ServiceId
  label: string
  icon: LucideIcon
  defaultHref: string
  items: NavItem[]
}

// Single source of truth for the service model. Order matters: the first entry
// is the fallback when a route belongs to no service (Config / auth are global).
export const SERVICES: Service[] = [
  {
    id: "briefing",
    label: "Briefing",
    icon: BookOpen,
    defaultHref: "/portfolio",
    items: [
      { href: "/portfolio", label: "Portfolio", icon: ChartPie },
      { href: "/watch-sectors", label: "Watch Sectors", icon: Globe },
      { href: "/geopolitical", label: "Geopolitical Risks", icon: Map },
      { href: "/run", label: "Run", icon: Play },
      { href: "/chat", label: "Q&A Chat", icon: MessageSquare },
      { href: "/briefing", label: "Briefing", icon: BookOpen },
    ],
  },
  {
    id: "journal",
    label: "Journal",
    icon: NotebookPen,
    defaultHref: "/journal",
    items: [{ href: "/journal", label: "Journal", icon: NotebookPen }],
  },
  {
    id: "monitor",
    label: "Monitor",
    icon: Activity,
    defaultHref: "/monitor",
    items: [{ href: "/monitor", label: "Monitor", icon: Activity }],
  },
  {
    id: "workspace",
    label: "Workspace",
    icon: FolderTree,
    defaultHref: "/workspace",
    items: [{ href: "/workspace", label: "Workspace", icon: FolderTree }],
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
