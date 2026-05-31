export type Theme = "light" | "dark"
export type Background = "default" | "soft"

export const THEMES: Theme[] = ["light", "dark"]
export const BACKGROUNDS: Background[] = ["default", "soft"]

export const THEME_STORAGE_KEY = "ai-agent:theme"
export const BACKGROUND_STORAGE_KEY = "ai-agent:background"

export function isTheme(v: unknown): v is Theme {
  return v === "light" || v === "dark"
}
export function isBackground(v: unknown): v is Background {
  return v === "default" || v === "soft"
}
