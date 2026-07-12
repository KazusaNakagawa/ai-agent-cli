import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ServiceTabs } from "@/components/ServiceTabs"
import { SERVICES } from "@/lib/services"

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

  it.each(SERVICES)(
    "renders the $id tab icon-only with an accessible name matching its label",
    (service) => {
      render(<ServiceTabs />)
      const tab = screen.getByTestId(`service-tab-${service.id}`)
      // Accessible name comes from a visually-hidden span, not aria-label/title,
      // so screen readers announce it exactly once (the icon glyph contributes
      // no name, so it's still the label alone in the accessibility tree).
      expect(screen.getByRole("link", { name: new RegExp(service.label) })).toBe(tab)
      expect(tab).not.toHaveAttribute("aria-label")
      expect(tab).not.toHaveAttribute("title")
      expect(tab).toHaveTextContent(service.icon)
    },
  )

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
