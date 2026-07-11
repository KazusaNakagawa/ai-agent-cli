import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { MonitorDashboard } from "@/components/screens/MonitorDashboard"
import { SERVICES } from "@/lib/services"

const MONITOR = {
  total_tokens: 1000,
  total_cost_usd: 12.34,
  by_project: [
    { key: "proj-a", tokens: 700, cost_usd: 10.0 },
    { key: "proj-b", tokens: 300, cost_usd: 2.34 },
  ],
  by_date: [
    {
      date: "2026-07-10",
      tokens: 600,
      cost_usd: 8.0,
      models: [
        { key: "claude-fable-5", tokens: 400, cost_usd: 7.0 },
        { key: "claude-sonnet-5", tokens: 200, cost_usd: 1.0 },
      ],
    },
    {
      date: "2026-07-11",
      tokens: 400,
      cost_usd: 4.34,
      models: [{ key: "claude-fable-5", tokens: 400, cost_usd: 4.34 }],
    },
  ],
  by_model: [
    { key: "claude-fable-5", tokens: 800, cost_usd: 11.34 },
    { key: "claude-sonnet-5", tokens: 200, cost_usd: 1.0 },
  ],
  unpriced_models: ["claude-future-9"],
}

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("MonitorDashboard", () => {
  it("renders totals, per-model legend, and breakdowns", async () => {
    fetchMock.mockResolvedValue(jsonResponse(MONITOR))
    render(<MonitorDashboard />)

    await waitFor(() =>
      expect(screen.getByTestId("monitor-total")).toHaveTextContent("$12.34"),
    )
    // Legend lists every model with a color swatch.
    const legend = screen.getByTestId("monitor-legend")
    expect(within(legend).getByText("claude-fable-5")).toBeInTheDocument()
    expect(within(legend).getByText("claude-sonnet-5")).toBeInTheDocument()
    const swatches = within(legend).getAllByTestId("monitor-legend-swatch")
    const colors = swatches.map((s) => s.style.backgroundColor)
    expect(new Set(colors).size).toBe(colors.length)

    // Stacked chart renders one segment per model per day, colored consistently.
    const segments = screen.getAllByTestId("monitor-stack-segment")
    expect(segments).toHaveLength(3) // 2 models on day 1 + 1 model on day 2
    const fableSegments = segments.filter(
      (s) => s.getAttribute("data-model") === "claude-fable-5",
    )
    expect(new Set(fableSegments.map((s) => s.style.backgroundColor)).size).toBe(1)

    // X-axis carries a short date label per bar (not just tooltips).
    const dateLabels = screen.getAllByTestId("monitor-stack-date-label")
    expect(dateLabels).toHaveLength(2)
    expect(dateLabels[0]).toHaveTextContent("Jul 10")
    expect(dateLabels[1]).toHaveTextContent("Jul 11")

    // Project and model breakdowns.
    expect(screen.getByTestId("monitor-by-project")).toHaveTextContent("proj-a")
    expect(screen.getByTestId("monitor-by-model")).toHaveTextContent("claude-sonnet-5")
    // API-equivalent estimate disclaimer.
    expect(screen.getByText(/API-equivalent/i)).toBeInTheDocument()
  })

  it("flags unpriced models", async () => {
    fetchMock.mockResolvedValue(jsonResponse(MONITOR))
    render(<MonitorDashboard />)
    await waitFor(() =>
      expect(screen.getByTestId("monitor-unpriced")).toHaveTextContent("claude-future-9"),
    )
  })

  it("switches metric and refetches on range change", async () => {
    fetchMock.mockResolvedValue(jsonResponse(MONITOR))
    render(<MonitorDashboard />)
    await waitFor(() => expect(screen.getByTestId("monitor-total")).toBeInTheDocument())

    // Default fetch happens once with a since param (default 7d range).
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toContain("since=")

    await userEvent.selectOptions(screen.getByTestId("monitor-metric-select"), "tokens")
    expect(screen.getByTestId("monitor-total")).toHaveTextContent("1,000")

    await userEvent.selectOptions(screen.getByTestId("monitor-range-select"), "all")
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(String(fetchMock.mock.calls[1][0])).not.toContain("since=")
  })

  it("shows an error state on fetch failure", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "boom" }, 500))
    render(<MonitorDashboard />)
    await waitFor(() =>
      expect(screen.getByTestId("monitor-error")).toHaveTextContent(/HTTP 500/),
    )
  })

  it("shows an error state on a rejected fetch (network failure)", async () => {
    fetchMock.mockRejectedValue(new Error("network"))
    render(<MonitorDashboard />)
    await waitFor(() =>
      expect(screen.getByTestId("monitor-error")).toHaveTextContent(/network/),
    )
  })

  it("shows an empty state when there is no data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        total_tokens: 0,
        total_cost_usd: 0,
        by_project: [],
        by_date: [],
        by_model: [],
        unpriced_models: [],
      }),
    )
    render(<MonitorDashboard />)
    await waitFor(() =>
      expect(screen.getByTestId("monitor-empty")).toBeInTheDocument(),
    )
  })
})

describe("services registration", () => {
  it("exposes a Monitor tab routed to /monitor", () => {
    const monitor = SERVICES.find((s) => s.id === "monitor")
    expect(monitor).toBeDefined()
    expect(monitor?.defaultHref).toBe("/monitor")
    expect(monitor?.label).toBe("Monitor")
  })
})
