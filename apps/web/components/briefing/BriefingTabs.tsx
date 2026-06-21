import { BriefingFile, briefingTypeLabel } from "@/lib/briefing-types"
import { cn } from "@/lib/utils"

// Sentinel for the "All" tab — must not collide with any real file type prefix.
export const ALL_TAB = "__all__"

interface BriefingTabsProps {
  files: BriefingFile[]
  selected: string
  onSelect: (type: string) => void
}

/** Unique types present in `files`, in first-seen order. */
export function tabTypes(files: BriefingFile[]): string[] {
  const seen = new Set<string>()
  const types: string[] = []
  for (const f of files) {
    if (!seen.has(f.type)) {
      seen.add(f.type)
      types.push(f.type)
    }
  }
  return types
}

/** Notion-like Type filter tabs: `All` first, then one tab per type present. */
export function BriefingTabs({ files, selected, onSelect }: BriefingTabsProps) {
  const types = tabTypes(files)

  return (
    <div data-testid="briefing-tabs" className="flex gap-1 border-b px-2 py-1">
      {[ALL_TAB, ...types].map((type) => (
        <button
          key={type}
          data-testid={`briefing-tab-${type}`}
          onClick={() => onSelect(type)}
          aria-selected={selected === type}
          className={cn(
            "rounded px-3 py-1 text-xs transition-colors",
            selected === type
              ? "bg-accent font-medium text-accent-foreground"
              : "text-muted-foreground hover:bg-accent/50",
          )}
        >
          {type === ALL_TAB ? "All" : briefingTypeLabel(type)}
        </button>
      ))}
    </div>
  )
}
