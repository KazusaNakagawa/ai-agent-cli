import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { buildBarTooltip, MonitorStackedChart } from "@/components/MonitorStackedChart"
import type { MonitorDateEntry } from "@/lib/monitor-types"

const DAY: MonitorDateEntry = {
  date: "2026-07-10",
  tokens: 600,
  cost_usd: 8,
  models: [
    { key: "claude-sonnet-5", tokens: 200, cost_usd: 1 },
    { key: "claude-fable-5", tokens: 400, cost_usd: 7 },
  ],
}

describe("buildBarTooltip", () => {
  it("lists every model of the day under a single date header", () => {
    expect(buildBarTooltip(DAY, "cost_usd")).toBe(
      ["Jul 10", "claude-fable-5: 7", "claude-sonnet-5: 1", "Total: 8"].join("\n"),
    )
  })

  it("follows the selected metric", () => {
    expect(buildBarTooltip(DAY, "tokens")).toBe(
      ["Jul 10", "claude-fable-5: 400", "claude-sonnet-5: 200", "Total: 600"].join("\n"),
    )
  })

  it("omits the total for a single-model day", () => {
    const day: MonitorDateEntry = { ...DAY, models: [DAY.models[1]] }
    expect(buildBarTooltip(day, "cost_usd")).toBe(["Jul 10", "claude-fable-5: 7"].join("\n"))
  })

  it("omits models with no usage on that day", () => {
    const day: MonitorDateEntry = {
      ...DAY,
      models: [...DAY.models, { key: "claude-future-9", tokens: 0, cost_usd: 0 }],
    }
    expect(buildBarTooltip(day, "cost_usd")).not.toContain("claude-future-9")
  })

  it("falls back to the date alone on an empty day", () => {
    expect(buildBarTooltip({ date: "2026-07-12", tokens: 0, cost_usd: 0, models: [] }, "cost_usd")).toBe(
      "Jul 12",
    )
  })

  it("keeps the raw date when it cannot be parsed", () => {
    const day: MonitorDateEntry = { ...DAY, date: "not-a-date" }
    expect(buildBarTooltip(day, "cost_usd").split("\n")[0]).toBe("not-a-date")
  })
})

describe("MonitorStackedChart", () => {
  const colorMap = { "claude-fable-5": "#111", "claude-sonnet-5": "#222" }

  it("puts the whole-bar tooltip on the bar and none on the segments", () => {
    render(<MonitorStackedChart byDate={[DAY]} metric="cost_usd" colorMap={colorMap} />)

    const bar = screen.getByTestId("monitor-stack-bar")
    expect(bar).toHaveAttribute("title", buildBarTooltip(DAY, "cost_usd"))
    for (const segment of screen.getAllByTestId("monitor-stack-segment")) {
      expect(segment).not.toHaveAttribute("title")
    }
  })
})
