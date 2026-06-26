import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ALL_TAB, BriefingTabs, tabTypes } from "@/components/briefing/BriefingTabs"
import { briefingTypeLabel, BriefingFile } from "@/lib/briefing-types"

const FILES: BriefingFile[] = [
  { name: "market_2026-06-21.md", type: "market", date: "2026-06-21", size: 10 },
  { name: "briefing_2026-06-20.md", type: "briefing", date: "2026-06-20", size: 10 },
  { name: "market_2026-06-19.md", type: "market", date: "2026-06-19", size: 10 },
  { name: "local_2026-06-18.md", type: "local", date: "2026-06-18", size: 10 },
]

describe("tabTypes", () => {
  it("returns unique types in first-seen order", () => {
    expect(tabTypes(FILES)).toEqual(["market", "briefing", "local"])
  })
})

describe("briefingTypeLabel", () => {
  it("maps known types and capitalizes unknown ones", () => {
    expect(briefingTypeLabel("briefing")).toBe("Briefing")
    expect(briefingTypeLabel("local")).toBe("Local")
    expect(briefingTypeLabel("weekly-summary")).toBe("Weekly")
    expect(briefingTypeLabel("market")).toBe("Market")
  })
})

describe("BriefingTabs", () => {
  it("renders All first, then one tab per type present, in order", () => {
    render(<BriefingTabs files={FILES} selected={ALL_TAB} onSelect={() => {}} />)
    const labels = Array.from(
      screen.getByTestId("briefing-tabs").querySelectorAll("button"),
    ).map((el) => el.textContent)
    expect(labels).toEqual(["All", "Market", "Briefing", "Local"])
  })

  it("calls onSelect with the clicked type", async () => {
    const onSelect = vi.fn()
    render(<BriefingTabs files={FILES} selected={ALL_TAB} onSelect={onSelect} />)
    await userEvent.setup().click(screen.getByTestId("briefing-tab-market"))
    expect(onSelect).toHaveBeenCalledWith("market")
  })
})
