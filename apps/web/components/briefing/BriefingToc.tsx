import type { RefObject } from "react"

import type { TocEntry } from "@/lib/briefing-toc"
import { cn } from "@/lib/utils"

interface BriefingTocProps {
  entries: TocEntry[]
  scrollContainer: RefObject<HTMLDivElement | null>
  activeId: string | null
  onClose: () => void
}

export function BriefingToc({ entries, scrollContainer, activeId, onClose }: BriefingTocProps) {
  if (entries.length === 0) return null

  const scrollTo = (id: string) => {
    const el = scrollContainer.current?.querySelector<HTMLElement>(`[id="${CSS.escape(id)}"]`)
    // scrollIntoView walks every scrollable ancestor and brings the heading to
    // the top. scroll-margin-top (set on the headings) keeps it clear of the
    // sticky header.
    el?.scrollIntoView({ behavior: "smooth", block: "start" })
    onClose()
  }

  return (
    <nav
      data-testid="briefing-toc"
      className="absolute right-0 top-0 bottom-0 w-56 overflow-y-auto border-l bg-background/30 px-3 py-4 backdrop-blur-sm"
    >
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        目次
      </p>
      <ul className="space-y-0.5">
        {entries.map((entry) => (
          <li key={entry.id}>
            <button
              onClick={() => scrollTo(entry.id)}
              className={cn(
                "w-full rounded px-2 py-1 text-left text-xs transition-colors hover:bg-accent hover:text-accent-foreground",
                entry.level === 1 && "font-medium",
                entry.level === 2 && "pl-4 text-muted-foreground",
                entry.level === 3 && "pl-6 text-muted-foreground/70",
                activeId === entry.id && "bg-accent/60 text-accent-foreground",
              )}
            >
              {entry.text}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}
