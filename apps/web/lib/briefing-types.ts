export type BriefingFile = {
  name: string
  type: string
  date: string // YYYY-MM-DD
  size: number // bytes
}

export type BriefingListResponse = {
  files: BriefingFile[]
}

export type BriefingFileResponse = {
  name: string
  content: string
}

const KNOWN_TYPE_LABELS: Record<string, string> = {
  briefing: "Briefing",
  local: "Local",
}

/** Map a type prefix to a display label: known → mapped, unknown → capitalized. */
export function briefingTypeLabel(type: string): string {
  return KNOWN_TYPE_LABELS[type] ?? (type ? type[0].toUpperCase() + type.slice(1) : type)
}
