import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Sidebar } from "@/components/Sidebar"
import { JobStateProvider } from "@/lib/jobStore"
import {
  SIDEBAR_COLLAPSED_ATTR as HTML_ATTR,
  SIDEBAR_COLLAPSED_KEY as COLLAPSED_KEY,
} from "@/lib/sidebar"

vi.mock("next/navigation", () => ({
  usePathname: () => "/portfolio",
}))

function renderSidebar() {
  return render(
    <JobStateProvider>
      <Sidebar />
    </JobStateProvider>,
  )
}

describe("Sidebar collapse", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    document.documentElement.removeAttribute(HTML_ATTR)
  })
  afterEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    document.documentElement.removeAttribute(HTML_ATTR)
  })

  it("starts expanded when neither the html attribute nor localStorage is set", () => {
    renderSidebar()
    expect(screen.getByTestId("sidebar")).toHaveAttribute(
      "data-collapsed",
      "false",
    )
    expect(document.documentElement.hasAttribute(HTML_ATTR)).toBe(false)
  })

  it("nav links always expose title and aria-label so tooltips work when collapsed", () => {
    renderSidebar()
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
    renderSidebar()

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

  it("syncs to the html attribute set by the pre-hydration script after mount", async () => {
    document.documentElement.setAttribute(HTML_ATTR, "true")
    renderSidebar()
    // First render matches SSR (collapsed=false) so React doesn't see a
    // hydration mismatch; the mount effect then promotes state to true.
    await waitFor(() => {
      expect(screen.getByTestId("sidebar")).toHaveAttribute(
        "data-collapsed",
        "true",
      )
    })
  })
})

describe("Config settings modal", () => {
  it("opens a modal with the four settings sections when Config is clicked", async () => {
    const user = userEvent.setup()
    renderSidebar()

    // Modal is closed initially.
    expect(screen.queryByTestId("settings-modal")).not.toBeInTheDocument()

    await user.click(screen.getByTestId("config-toggle"))

    expect(screen.getByTestId("settings-modal")).toBeInTheDocument()
    for (const key of ["usage", "appearance", "config-file", "export"]) {
      expect(screen.getByTestId(`settings-nav-${key}`)).toBeInTheDocument()
    }
  })

  it("switches the content pane when a section is selected", async () => {
    const user = userEvent.setup()
    renderSidebar()
    await user.click(screen.getByTestId("config-toggle"))

    // Export section panel renders only after selecting it.
    expect(screen.queryByTestId("output-export-panel")).not.toBeInTheDocument()
    await user.click(screen.getByTestId("settings-nav-export"))
    expect(screen.getByTestId("output-export-panel")).toBeInTheDocument()
  })
})
