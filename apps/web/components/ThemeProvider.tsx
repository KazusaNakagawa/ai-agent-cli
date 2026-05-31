"use client"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"

import {
  Background,
  BACKGROUND_STORAGE_KEY,
  isBackground,
  isTheme,
  Theme,
  THEME_STORAGE_KEY,
} from "@/lib/theme"

type Ctx = {
  theme: Theme
  background: Background
  setTheme: (t: Theme) => void
  setBackground: (b: Background) => void
}

const ThemeContext = createContext<Ctx | null>(null)

// Reads the current state already painted onto <html> by the pre-hydration
// script (see app/layout.tsx). Defaults are conservative for SSR — the
// pre-hydration script has already corrected the DOM before this mounts.
function readInitialTheme(): Theme {
  if (typeof document === "undefined") return "light"
  return document.documentElement.classList.contains("dark") ? "dark" : "light"
}
function readInitialBackground(): Background {
  if (typeof document === "undefined") return "default"
  const v = document.documentElement.getAttribute("data-bg")
  return isBackground(v) ? v : "default"
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readInitialTheme)
  const [background, setBackgroundState] =
    useState<Background>(readInitialBackground)

  // Keep <html> in sync if state changes after mount (e.g. via the panel).
  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", theme === "dark")
  }, [theme])

  useEffect(() => {
    document.documentElement.setAttribute("data-bg", background)
  }, [background])

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, t)
    } catch {
      // localStorage may be unavailable (private mode, quota); the class
      // toggle still works for the session.
    }
  }, [])

  const setBackground = useCallback((b: Background) => {
    setBackgroundState(b)
    try {
      localStorage.setItem(BACKGROUND_STORAGE_KEY, b)
    } catch {
      // see above
    }
  }, [])

  const value = useMemo<Ctx>(
    () => ({ theme, background, setTheme, setBackground }),
    [theme, background, setTheme, setBackground],
  )
  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  )
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider")
  return ctx
}

// Inline script that runs before React hydration, applied via dangerouslySet-
// InnerHTML in app/layout.tsx. It must be self-contained, defensive against
// missing storage, and idempotent.
export const themeBootScript = `
(function(){try{
  var t = localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
  if (t !== "light" && t !== "dark") {
    t = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  }
  if (t === "dark") document.documentElement.classList.add("dark");
  var b = localStorage.getItem(${JSON.stringify(BACKGROUND_STORAGE_KEY)});
  if (b !== "default" && b !== "soft") b = "default";
  document.documentElement.setAttribute("data-bg", b);
}catch(e){}})();
`

// Re-export helpers so tests / consumers can avoid importing two modules.
export { isBackground, isTheme }
export type { Background, Theme }
