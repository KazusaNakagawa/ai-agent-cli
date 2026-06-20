import { BriefingFile, BRIEFING_TYPE_LABELS } from "@/lib/briefing-types"
import { cn } from "@/lib/utils"

import { ExternalLinkIcon } from "./icons"

interface BriefingRowProps {
  file: BriefingFile
  selected: boolean
  onOpen: (file: BriefingFile) => void
  onHover: (file: BriefingFile) => void
}

export function BriefingRow({ file, selected, onOpen, onHover }: BriefingRowProps) {
  return (
    <tr
      data-testid={`briefing-row-${file.name}`}
      tabIndex={0}
      aria-selected={selected}
      onMouseEnter={() => onHover(file)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onOpen(file)
        }
      }}
      className={cn(
        "group border-b text-xs transition-colors last:border-0",
        selected ? "bg-accent font-medium text-accent-foreground" : "hover:bg-accent/50",
      )}
    >
      <td className="max-w-[160px] truncate px-3 py-2" title={file.name}>
        {file.name}
      </td>
      <td className="px-3 py-2">{BRIEFING_TYPE_LABELS[file.type]}</td>
      <td className="px-3 py-2 tabular-nums">{file.date}</td>
      <td className="px-2 py-2">
        <button
          data-testid={`briefing-open-${file.name}`}
          onClick={() => onOpen(file)}
          aria-label={`Open ${file.name}`}
          className="rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-accent-foreground focus:opacity-100 group-hover:opacity-100"
        >
          <ExternalLinkIcon />
        </button>
      </td>
    </tr>
  )
}
