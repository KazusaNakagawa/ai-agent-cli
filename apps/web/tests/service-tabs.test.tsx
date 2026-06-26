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
