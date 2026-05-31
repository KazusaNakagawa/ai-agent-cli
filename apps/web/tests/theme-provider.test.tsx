import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { AppearancePanel } from "@/components/AppearancePanel"
import { ThemeProvider } from "@/components/ThemeProvider"
import {
  BACKGROUND_STORAGE_KEY,
  THEME_STORAGE_KEY,
} from "@/lib/theme"

describe("ThemeProvider + AppearancePanel", () => {
  beforeEach(() => {
    document.documentElement.className = ""
    document.documentElement.removeAttribute("data-bg")
    localStorage.clear()
  })
  afterEach(() => {
    document.documentElement.className = ""
    document.documentElement.removeAttribute("data-bg")
    localStorage.clear()
  })

  it("applies the 'dark' class on documentElement when Dark is selected", async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <AppearancePanel />
      </ThemeProvider>,
    )
    expect(document.documentElement.classList.contains("dark")).toBe(false)
    await user.click(screen.getByTestId("theme-dark"))
    expect(document.documentElement.classList.contains("dark")).toBe(true)
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark")
  })

  it("sets data-bg attribute and persists the background choice", async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <AppearancePanel />
      </ThemeProvider>,
    )
    await user.click(screen.getByTestId("bg-soft"))
    expect(document.documentElement.getAttribute("data-bg")).toBe("soft")
    expect(localStorage.getItem(BACKGROUND_STORAGE_KEY)).toBe("soft")
  })
})
