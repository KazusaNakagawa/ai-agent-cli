import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Sidebar } from "@/components/Sidebar"

vi.mock("next/navigation", () => ({
  usePathname: () => "/portfolio",
}))

const COLLAPSED_KEY = "ai-agent:sidebar-collapsed"

describe("Sidebar collapse", () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it("starts expanded by default with labels visible", () => {
    render(<Sidebar />)
    expect(screen.getByTestId("sidebar")).toHaveAttribute(
      "data-collapsed",
      "false",
    )
    expect(screen.getByText("Portfolio")).toBeInTheDocument()
    expect(screen.getByText("Config")).toBeInTheDocument()
  })

  it("toggles to icon-only mode, hides labels, exposes accessible names", async () => {
    const user = userEvent.setup()
    render(<Sidebar />)
    await user.click(screen.getByTestId("sidebar-toggle"))
    const sidebar = screen.getByTestId("sidebar")
    expect(sidebar).toHaveAttribute("data-collapsed", "true")
    // Text labels gone, Config section hidden, accessible name preserved.
    expect(screen.queryByText("Portfolio")).not.toBeInTheDocument()
    expect(screen.queryByText("Config")).not.toBeInTheDocument()
    expect(screen.getByTestId("nav-portfolio")).toHaveAttribute(
      "aria-label",
      "Portfolio",
    )
    expect(screen.getByTestId("nav-portfolio")).toHaveAttribute(
      "title",
      "Portfolio",
    )
  })

  it("persists collapsed=true across renders via localStorage", async () => {
    const user = userEvent.setup()
    const { unmount } = render(<Sidebar />)
    await user.click(screen.getByTestId("sidebar-toggle"))
    expect(localStorage.getItem(COLLAPSED_KEY)).toBe("true")
    unmount()

    render(<Sidebar />)
    await waitFor(() => {
      expect(screen.getByTestId("sidebar")).toHaveAttribute(
        "data-collapsed",
        "true",
      )
    })
  })

  it("ignores a missing or non-true localStorage value (default expanded)", async () => {
    localStorage.setItem(COLLAPSED_KEY, "garbage")
    render(<Sidebar />)
    await waitFor(() => {
      expect(screen.getByTestId("sidebar")).toHaveAttribute(
        "data-collapsed",
        "false",
      )
    })
  })
})
