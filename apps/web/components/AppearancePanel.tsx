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

export function AppearancePanel() {
  const { theme, background, setTheme, setBackground } = useTheme()
  return (
    <div className="space-y-2 border-t pt-3" data-testid="appearance-panel">
      <p className="px-2 text-[10px] font-medium uppercase text-muted-foreground">
        Appearance
      </p>
      <div className="space-y-1">
        <p className="px-2 text-xs text-muted-foreground">Theme</p>
        <div className="flex gap-1 px-2">
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
        <p className="px-2 text-xs text-muted-foreground">Background</p>
        <div className="flex gap-1 px-2">
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
