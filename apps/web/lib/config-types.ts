// Mirror of apps/python/src/config.BriefingFileConfig so the form
// payloads we PUT match the backend's Pydantic schema exactly.
// Keep these in sync with src/config.py.

export type Portfolio = {
  tickers: string[]
  themes: string[]
}

export type WatchSector = {
  sector: string
  tickers: string[]
  notes: string | null
}

export type Conflict = {
  name: string
  affected_sectors: string[]
  related_tickers: string[]
  notes: string | null
}

export type Geopolitical = {
  conflicts: Conflict[]
}

export type WatchEvent = {
  name: string
  trigger: string
  affected_sectors: string[]
  related_tickers: string[]
  notes: string | null
}

export type BriefingConfig = {
  portfolio: Portfolio
  geopolitical: Geopolitical
  watch_sectors: WatchSector[]
  watch_events: WatchEvent[]
}
