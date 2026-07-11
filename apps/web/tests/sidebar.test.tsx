import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Sidebar } from "@/components/Sidebar"
import { JobStateProvider } from "@/lib/jobStore"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"
import { JournalNavProvider } from "@/lib/journalNavStore"
import {
  SIDEBAR_COLLAPSED_ATTR as HTML_ATTR,
  SIDEBAR_COLLAPSED_KEY as COLLAPSED_KEY,
} from "@/lib/sidebar"

let mockPathname = "/portfolio"
vi.mock("next/navigation", () => ({ usePathname: () => mockPathname }))

function renderSidebar() {
  return render(
    <JobStateProvider>
      <JournalChatStateProvider>
        <JournalChatJobStateProvider>
          <JournalNavProvider>
            <Sidebar />
          </JournalNavProvider>
        </JournalChatJobStateProvider>
      </JournalChatStateProvider>
    </JobStateProvider>,
  )
}

describe("Sidebar collapse", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    document.documentElement.removeAttribute(HTML_ATTR)
    mockPathname = "/portfolio"
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

  it("shows a resize handle when expanded and hides it when collapsed", async () => {
    const user = userEvent.setup()
    renderSidebar()
    expect(screen.getByTestId("sidebar-resizer")).toBeInTheDocument()
    await user.click(screen.getByTestId("sidebar-toggle"))
    expect(screen.queryByTestId("sidebar-resizer")).not.toBeInTheDocument()
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
  beforeEach(() => {
    mockPathname = "/portfolio"
  })

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

    // Usage is the default active section on open.
    expect(screen.getByTestId("settings-nav-usage")).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByTestId("settings-section-usage")).toBeInTheDocument()
    for (const key of ["appearance", "config-file", "export"]) {
      expect(screen.getByTestId(`settings-nav-${key}`)).toHaveAttribute(
        "aria-selected",
        "false",
      )
    }
  })

  it("switches the content pane and aria-selected when a section is selected", async () => {
    const user = userEvent.setup()
    renderSidebar()
    await user.click(screen.getByTestId("config-toggle"))

    // Export section panel renders only after selecting it.
    expect(screen.queryByTestId("output-export-panel")).not.toBeInTheDocument()
    await user.click(screen.getByTestId("settings-nav-export"))
    expect(screen.getByTestId("output-export-panel")).toBeInTheDocument()
    expect(screen.getByTestId("settings-nav-export")).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByTestId("settings-nav-usage")).toHaveAttribute(
      "aria-selected",
      "false",
    )
  })

  it("resets to the first section when reopened", async () => {
    const user = userEvent.setup()
    renderSidebar()

    await user.click(screen.getByTestId("config-toggle"))
    await user.click(screen.getByTestId("settings-nav-export"))
    expect(screen.getByTestId("settings-section-export")).toBeInTheDocument()

    // Close (Esc) and reopen — should default back to Usage.
    await user.keyboard("{Escape}")
    await user.click(screen.getByTestId("config-toggle"))
    expect(screen.getByTestId("settings-section-usage")).toBeInTheDocument()
  })
})

describe("Sidebar service items", () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute(HTML_ATTR)
    mockPathname = "/portfolio"
  })

  const BRIEFING_NAV_IDS = [
    "nav-portfolio",
    "nav-watch-sectors",
    "nav-geopolitical",
    "nav-run",
    "nav-chat",
    "nav-briefing",
  ]
  const JOURNAL_NAV_IDS = ["nav-journal"]

  it("shows the six Briefing items and hides Journal on a briefing route", () => {
    mockPathname = "/portfolio"
    renderSidebar()
    for (const id of BRIEFING_NAV_IDS) {
      expect(screen.getByTestId(id)).toBeInTheDocument()
    }
    for (const id of JOURNAL_NAV_IDS) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument()
    }
  })

  it("shows only the Journal item and hides Briefing on a journal route", () => {
    mockPathname = "/journal"
    renderSidebar()
    for (const id of JOURNAL_NAV_IDS) {
      expect(screen.getByTestId(id)).toBeInTheDocument()
    }
    for (const id of BRIEFING_NAV_IDS) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument()
    }
  })
})
