export type BriefingFile = {
  name: string
  type: "briefing" | "local"
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

export const BRIEFING_TYPE_LABELS: Record<BriefingFile["type"], string> = {
  briefing: "Briefing",
  local: "Local",
}
