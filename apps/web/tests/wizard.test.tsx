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
    watch_sectors: [
      // Synthesised by the first run to mirror the portfolio.
      { sector: "Default", tickers: ["GOOGL", "MSFT"], notes: null },
      { sector: "Cloud", tickers: ["MSFT"], notes: "keep me" },
    ],
    watch_events: [
      { name: "FOMC", trigger: "rate hike", affected_sectors: [], related_tickers: [], notes: null },
    ],
  }

  // Route by URL + method so the parallel prefill GETs don't depend on order.
  const routeFetch = (
    config: () => Response,
    put: (url: string) => Response = () => new Response("{}", { status: 200 }),
  ) =>
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET"
      if (method === "PUT") return put(url)
      if (url === "/api/auth/mode") {
        return new Response(JSON.stringify({ auth_mode: "api" }), { status: 200 })
      }
      if (url === "/api/config") return config()
      return new Response("{}", { status: 200 })
    })
  const existingConfig = () => new Response(JSON.stringify(EXISTING), { status: 200 })

  const putBodies = (url: string) =>
    fetchMock.mock.calls
      .filter(([u, init]) => u === url && (init as RequestInit | undefined)?.method === "PUT")
      .map(([, init]) => JSON.parse((init as RequestInit).body as string))

  const advanceToStep3 = async (user: ReturnType<typeof userEvent.setup>, tickers: string) => {
    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /Anthropic API key/ })).toBeChecked()
    })
    await user.click(screen.getByRole("radio", { name: /Claude Pro/ }))
    await user.click(screen.getByTestId("wizard-primary"))
    await waitFor(() => expect(screen.getByTestId("tickers-input")).toBeInTheDocument())
    await user.clear(screen.getByTestId("tickers-input"))
    await user.type(screen.getByTestId("tickers-input"), tickers)
    await user.click(screen.getByTestId("wizard-primary"))
    await waitFor(() => expect(screen.getByText(/Step 3 \/ 4/)).toBeInTheDocument())
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
    routeFetch(existingConfig)
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

    await waitFor(() => expect(putBodies("/api/config")).toHaveLength(1))
    expect(putBodies("/api/auth/mode")).toEqual([{ auth_mode: "api" }])
    expect(putBodies("/api/config")[0]).toEqual({
      ...EXISTING,
      portfolio: { tickers: ["PLTR"], themes: ["AI"] },
      // The mirrored Default sector follows the new tickers; others are kept.
      watch_sectors: [
        { sector: "Default", tickers: ["PLTR"], notes: null },
        { sector: "Cloud", tickers: ["MSFT"], notes: "keep me" },
      ],
    })
  })

  it("leaves a Default sector alone once the user has edited it", async () => {
    const edited = {
      ...EXISTING,
      watch_sectors: [{ sector: "Default", tickers: ["MSFT", "NVDA"], notes: null }],
    }
    routeFetch(() => new Response(JSON.stringify(edited), { status: 200 }))
    const user = userEvent.setup()
    render(<Wizard rerun />)

    await advanceToStep3(user, "PLTR")

    expect(putBodies("/api/config")[0].watch_sectors).toEqual(edited.watch_sectors)
  })

  it("falls back to a fresh config only when briefing.json is missing (404)", async () => {
    routeFetch(() => new Response("not found", { status: 404 }))
    const user = userEvent.setup()
    render(<Wizard rerun />)

    await advanceToStep3(user, "PLTR")

    expect(putBodies("/api/config")[0]).toEqual({
      portfolio: { tickers: ["PLTR"], themes: [] },
      watch_sectors: [{ sector: "Default", tickers: ["PLTR"], notes: null }],
      geopolitical: { conflicts: [] },
      watch_events: [],
    })
  })

  it("blocks the wizard when the current config cannot be read", async () => {
    routeFetch(() => new Response("boom", { status: 500 }))
    render(<Wizard rerun />)

    await waitFor(() => {
      expect(screen.getByTestId("wizard-load-error")).toHaveTextContent(/500/)
    })
    expect(screen.queryByTestId("wizard-primary")).not.toBeInTheDocument()
    expect(screen.getByTestId("wizard-cancel-rerun")).toBeInTheDocument()
  })

  it("cancel before saving anything just navigates back", async () => {
    routeFetch(existingConfig)
    const user = userEvent.setup()
    render(<Wizard rerun />)
    await waitFor(() => expect(screen.getByTestId("wizard-primary")).toBeInTheDocument())

    await user.click(screen.getByTestId("wizard-cancel-rerun"))

    await waitFor(() => expect(assignMock).toHaveBeenCalledWith("/portfolio"))
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "PUT")).toBe(false)
  })

  it("cancel after saving restores the original auth mode and config", async () => {
    routeFetch(existingConfig)
    const user = userEvent.setup()
    render(<Wizard rerun />)
    await advanceToStep3(user, "PLTR")

    await user.click(screen.getByTestId("wizard-cancel-rerun"))

    await waitFor(() => expect(assignMock).toHaveBeenCalledWith("/portfolio"))
    expect(putBodies("/api/auth/mode")).toEqual([{ auth_mode: "cli" }, { auth_mode: "api" }])
    expect(putBodies("/api/config").at(-1)).toEqual(EXISTING)
  })

  it("cancel surfaces an error and stays when the restore fails", async () => {
    let restoring = false
    routeFetch(existingConfig, (url) => {
      if (restoring && url === "/api/config") return new Response("boom", { status: 500 })
      return new Response("{}", { status: 200 })
    })
    const user = userEvent.setup()
    render(<Wizard rerun />)
    await advanceToStep3(user, "PLTR")

    restoring = true
    await user.click(screen.getByTestId("wizard-cancel-rerun"))

    await waitFor(() => {
      expect(screen.getByTestId("wizard-cancel-error")).toHaveTextContent(/500/)
    })
    expect(assignMock).not.toHaveBeenCalled()
  })
})
