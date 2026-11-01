import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Wizard } from "@/components/onboarding/Wizard"

describe("Wizard", () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders Step 1 by default", () => {
    render(<Wizard />)
    expect(screen.getByText(/Step 1 \/ 4/)).toBeInTheDocument()
    expect(screen.getByText(/Choose how to call Claude/)).toBeInTheDocument()
  })

  it("advances from Step 1 to Step 2 after PUT /api/auth/mode succeeds", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ auth_mode: "cli" }), { status: 200 }),
    )
    const user = userEvent.setup()
    render(<Wizard />)

    await user.click(screen.getByTestId("wizard-primary"))

    await waitFor(() => {
      expect(screen.getByText(/Step 2 \/ 4/)).toBeInTheDocument()
    })
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/mode",
      expect.objectContaining({ method: "PUT" }),
    )
    expect(screen.getByTestId("tickers-input")).toBeInTheDocument()
  })

  it("surfaces a Step 1 error when PUT /api/auth/mode fails", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("boom", { status: 500 }),
    )
    const user = userEvent.setup()
    render(<Wizard />)

    await user.click(screen.getByTestId("wizard-primary"))

    await waitFor(() => {
      expect(screen.getByTestId("wizard-error")).toHaveTextContent(/500/)
    })
    expect(screen.getByText(/Step 1 \/ 4/)).toBeInTheDocument()
  })

  it("does not load existing settings or offer cancel on a first run", () => {
    render(<Wizard />)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.queryByTestId("wizard-cancel-rerun")).not.toBeInTheDocument()
  })
})

describe("Wizard re-run mode", () => {
  const fetchMock = vi.fn()
  const assignMock = vi.fn()

  const EXISTING = {
    portfolio: { tickers: ["MSFT", "GOOGL"], themes: ["AI"] },
    geopolitical: {
      conflicts: [
        { name: "Hormuz", affected_sectors: ["Energy"], related_tickers: ["XOM"], notes: null },
      ],
    },
    watch_sectors: [{ sector: "Cloud", tickers: ["MSFT"], notes: "keep me" }],
    watch_events: [
      { name: "FOMC", trigger: "rate hike", affected_sectors: [], related_tickers: [], notes: null },
    ],
  }

  // Route by URL + method so the parallel prefill GETs don't depend on order.
  const routeFetch = (config: Response | (() => Response)) =>
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET"
      if (url === "/api/auth/mode" && method === "GET") {
        return new Response(JSON.stringify({ auth_mode: "api" }), { status: 200 })
      }
      if (url === "/api/config" && method === "GET") {
        return typeof config === "function" ? config() : config
      }
      return new Response("{}", { status: 200 })
    })

  const putBody = (url: string) => {
    const call = fetchMock.mock.calls.find(
      ([u, init]) => u === url && (init as RequestInit | undefined)?.method === "PUT",
    )
    return call ? JSON.parse((call[1] as RequestInit).body as string) : undefined
  }

  beforeEach(() => {
    fetchMock.mockReset()
    assignMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("location", { ...window.location, assign: assignMock })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("prefills from current settings and keeps unrelated config on save", async () => {
    routeFetch(() => new Response(JSON.stringify(EXISTING), { status: 200 }))
    const user = userEvent.setup()
    render(<Wizard rerun />)

    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /Anthropic API key/ })).toBeChecked()
    })
    await user.click(screen.getByTestId("wizard-primary"))

    await waitFor(() => {
      expect(screen.getByTestId("tickers-input")).toHaveValue("MSFT, GOOGL")
    })
    expect(screen.getByTestId("themes-input")).toHaveValue("AI")
    await user.clear(screen.getByTestId("tickers-input"))
    await user.type(screen.getByTestId("tickers-input"), "PLTR")
    await user.click(screen.getByTestId("wizard-primary"))

    await waitFor(() => expect(putBody("/api/config")).toBeDefined())
    expect(putBody("/api/auth/mode")).toEqual({ auth_mode: "api" })
    expect(putBody("/api/config")).toEqual({
      ...EXISTING,
      portfolio: { tickers: ["PLTR"], themes: ["AI"] },
    })
  })

  it("falls back to a fresh config when briefing.json is missing", async () => {
    routeFetch(() => new Response("not found", { status: 404 }))
    const user = userEvent.setup()
    render(<Wizard rerun />)

    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /Anthropic API key/ })).toBeChecked()
    })
    await user.click(screen.getByTestId("wizard-primary"))
    await waitFor(() => expect(screen.getByTestId("tickers-input")).toHaveValue(""))
    await user.type(screen.getByTestId("tickers-input"), "PLTR")
    await user.click(screen.getByTestId("wizard-primary"))

    await waitFor(() => expect(putBody("/api/config")).toBeDefined())
    expect(putBody("/api/config")).toEqual({
      portfolio: { tickers: ["PLTR"], themes: [] },
      watch_sectors: [{ sector: "Default", tickers: ["PLTR"], notes: null }],
      geopolitical: { conflicts: [] },
      watch_events: [],
    })
  })

  it("cancel restores onboarded and returns to the app", async () => {
    routeFetch(() => new Response(JSON.stringify(EXISTING), { status: 200 }))
    const user = userEvent.setup()
    render(<Wizard rerun />)

    await user.click(screen.getByTestId("wizard-cancel-rerun"))

    await waitFor(() => expect(assignMock).toHaveBeenCalledWith("/portfolio"))
    expect(putBody("/api/state")).toEqual({ onboarded: true })
  })

  it("cancel surfaces an error when PUT /api/state fails", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/state" && init?.method === "PUT") {
        return new Response("boom", { status: 500 })
      }
      return new Response("not found", { status: 404 })
    })
    const user = userEvent.setup()
    render(<Wizard rerun />)

    await user.click(screen.getByTestId("wizard-cancel-rerun"))

    await waitFor(() => {
      expect(screen.getByTestId("wizard-cancel-error")).toHaveTextContent(/500/)
    })
    expect(assignMock).not.toHaveBeenCalled()
  })
})
