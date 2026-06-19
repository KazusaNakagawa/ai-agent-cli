import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { UsageDashboard } from "@/components/screens/UsageDashboard"

const DATES = { dates: ["20260620", "20260619"] }
const DAY_20620 = {
  date: "20260620",
  records: [
    {
      timestamp: "2026-06-20T05:06:30",
      label: "セクタースイープ",
      input_tokens: 3445,
      output_tokens: 6061,
      cache_read_tokens: 165437,
      cache_creation_tokens: 33895,
      cost_usd: 0.827,
      duration_ms: 186627,
    },
    {
      timestamp: "2026-06-20T05:05:17",
      label: "メイン分析",
      input_tokens: 787,
      output_tokens: 4546,
      cache_read_tokens: 95729,
      cache_creation_tokens: 23308,
      cost_usd: 0.468,
      duration_ms: 113321,
    },
  ],
}

const fetchMock = vi.fn()

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  })
}

describe("UsageDashboard", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("loads newest date and renders one bar per record", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/usage/dates")) return Promise.resolve(jsonResponse(DATES))
      return Promise.resolve(jsonResponse(DAY_20620))
    })

    render(<UsageDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId("usage-bar-chart")).toBeInTheDocument()
    })
    expect(screen.getByTestId("usage-bar-0")).toBeInTheDocument()
    expect(screen.getByTestId("usage-bar-1")).toBeInTheDocument()
    // Newest date selected by default.
    expect(screen.getByTestId("usage-date-select")).toHaveValue("20260620")
  })

  it("re-fetches when the date is changed", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/usage/dates")) return Promise.resolve(jsonResponse(DATES))
      return Promise.resolve(jsonResponse({ date: "20260619", records: [] }))
    })

    render(<UsageDashboard />)
    await waitFor(() => expect(screen.getByTestId("usage-date-select")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.selectOptions(screen.getByTestId("usage-date-select"), "20260619")

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => c[0] as string)
      expect(urls.some((u) => u.includes("date=20260619"))).toBe(true)
    })
  })

  it("shows a no-dates message when there are no logs", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ dates: [] }))
    render(<UsageDashboard />)
    await waitFor(() => {
      expect(screen.getByTestId("usage-no-dates")).toBeInTheDocument()
    })
  })
})
