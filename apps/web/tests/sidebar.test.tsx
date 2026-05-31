import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Sidebar } from "@/components/Sidebar"

vi.mock("next/navigation", () => ({
  usePathname: () => "/portfolio",
}))

const COLLAPSED_KEY = "ai-agent:sidebar-collapsed"
const HTML_ATTR = "data-sidebar-collapsed"

describe("Sidebar collapse", () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute(HTML_ATTR)
  })
  afterEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute(HTML_ATTR)
  })

  it("starts expanded when neither the html attribute nor localStorage is set", () => {
    render(<Sidebar />)
    expect(screen.getByTestId("sidebar")).toHaveAttribute(
      "data-collapsed",
      "false",
    )
    expect(document.documentElement.hasAttribute(HTML_ATTR)).toBe(false)
  })

  it("nav links always expose title and aria-label so tooltips work when collapsed", () => {
    render(<Sidebar />)
    expect(screen.getByTestId("nav-portfolio")).toHaveAttribute(
      "title",
      "Portfolio",
    )
    expect(screen.getByTestId("nav-portfolio")).toHaveAttribute(
      "aria-label",
      "Portfolio",
    )
  })

  it("toggle writes html attribute + localStorage and round-trips", async () => {
    const user = userEvent.setup()
    render(<Sidebar />)

    await user.click(screen.getByTestId("sidebar-toggle"))
    expect(document.documentElement.getAttribute(HTML_ATTR)).toBe("true")
    expect(localStorage.getItem(COLLAPSED_KEY)).toBe("true")
    expect(screen.getByTestId("sidebar")).toHaveAttribute(
      "data-collapsed",
      "true",
    )

    await user.click(screen.getByTestId("sidebar-toggle"))
    expect(document.documentElement.hasAttribute(HTML_ATTR)).toBe(false)
    expect(localStorage.getItem(COLLAPSED_KEY)).toBe("false")
    expect(screen.getByTestId("sidebar")).toHaveAttribute(
      "data-collapsed",
      "false",
    )
  })

  it("reads initial collapsed state from the html attribute (pre-hydration path)", () => {
    document.documentElement.setAttribute(HTML_ATTR, "true")
    render(<Sidebar />)
    expect(screen.getByTestId("sidebar")).toHaveAttribute(
      "data-collapsed",
      "true",
    )
  })
})
