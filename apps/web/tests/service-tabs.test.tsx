import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ServiceTabs } from "@/components/ServiceTabs"

// Mutable pathname so each test can place itself on a different route.
let mockPathname = "/portfolio"
vi.mock("next/navigation", () => ({ usePathname: () => mockPathname }))
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: any) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

afterEach(() => { mockPathname = "/portfolio" })

describe("ServiceTabs", () => {
  it("renders one tab per service linking to its defaultHref", () => {
    render(<ServiceTabs />)
    const briefing = screen.getByTestId("service-tab-briefing")
    const journal = screen.getByTestId("service-tab-journal")
    expect(briefing).toHaveAttribute("href", "/portfolio")
    expect(journal).toHaveAttribute("href", "/journal")
  })

  it("renders each tab icon-only with an accessible label matching the service name", () => {
    render(<ServiceTabs />)
    const workspace = screen.getByTestId("service-tab-workspace")
    expect(workspace).toHaveAttribute("aria-label", "Workspace")
    expect(workspace).toHaveTextContent("🗂️")
    expect(workspace).not.toHaveTextContent("Workspace")
  })

  it("does not render any visible text label in the tab bar", () => {
    render(<ServiceTabs />)
    expect(screen.queryByText("Briefing")).not.toBeInTheDocument()
    expect(screen.queryByText("Journal")).not.toBeInTheDocument()
    expect(screen.queryByText("Monitor")).not.toBeInTheDocument()
    expect(screen.queryByText("Workspace")).not.toBeInTheDocument()
  })

  it("marks the briefing tab active on a briefing route", () => {
    mockPathname = "/chat"
    render(<ServiceTabs />)
    expect(screen.getByTestId("service-tab-briefing")).toHaveAttribute("aria-current", "page")
    expect(screen.getByTestId("service-tab-journal")).not.toHaveAttribute("aria-current")
  })

  it("marks the journal tab active on a journal route", () => {
    mockPathname = "/journal"
    render(<ServiceTabs />)
    expect(screen.getByTestId("service-tab-journal")).toHaveAttribute("aria-current", "page")
    expect(screen.getByTestId("service-tab-briefing")).not.toHaveAttribute("aria-current")
  })
})
