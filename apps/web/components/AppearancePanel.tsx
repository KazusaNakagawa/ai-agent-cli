"use client"
import { useTheme } from "@/components/ThemeProvider"
import { cn } from "@/lib/utils"
import {
  Background,
  BACKGROUNDS,
  Theme,
  THEMES,
} from "@/lib/theme"

const THEME_LABEL: Record<Theme, string> = {
  light: "Light",
  dark: "Dark",
}
const BG_LABEL: Record<Background, string> = {
  default: "Default",
  soft: "Soft",
}

// Renders only the Theme + Background controls. The "Appearance" label and
// any surrounding disclosure live in the Sidebar so this panel can be reused
// from a future /appearance route without duplicating the heading.
export function AppearancePanel() {
  const { theme, background, setTheme, setBackground } = useTheme()
  return (
    <div className="space-y-2" data-testid="appearance-panel">
      <div className="space-y-1">
        <p className="text-[10px] uppercase text-muted-foreground">Theme</p>
        <div className="flex gap-1">
          {THEMES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTheme(t)}
              aria-pressed={theme === t}
              data-testid={`theme-${t}`}
              className={cn(
                "flex-1 rounded-md border px-2 py-1 text-xs transition-colors",
                theme === t
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input hover:bg-accent",
              )}
            >
              {THEME_LABEL[t]}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-1">
        <p className="text-[10px] uppercase text-muted-foreground">
          Background
        </p>
        <div className="flex gap-1">
          {BACKGROUNDS.map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => setBackground(b)}
              aria-pressed={background === b}
              data-testid={`bg-${b}`}
              className={cn(
                "flex-1 rounded-md border px-2 py-1 text-xs transition-colors",
                background === b
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input hover:bg-accent",
              )}
            >
              {BG_LABEL[b]}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
