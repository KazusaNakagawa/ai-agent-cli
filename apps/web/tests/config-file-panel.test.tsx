import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ConfigFilePanel } from "@/components/ConfigFilePanel"

const refreshMock = vi.fn()
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
}))

describe("ConfigFilePanel", () => {
  const fetchMock = vi.fn()
  const clickSpy = vi.fn()
  const originalCreateObjectURL = URL.createObjectURL
  const originalRevokeObjectURL = URL.revokeObjectURL

  beforeEach(() => {
    fetchMock.mockReset()
    clickSpy.mockReset()
    refreshMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    // Override per-element click via HTMLAnchorElement.prototype so the
    // download trigger doesn't actually navigate jsdom.
    HTMLAnchorElement.prototype.click = clickSpy
    URL.createObjectURL = vi.fn(() => "blob:fake")
    URL.revokeObjectURL = vi.fn()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    URL.createObjectURL = originalCreateObjectURL
    URL.revokeObjectURL = originalRevokeObjectURL
  })

  it("Export triggers a download with the GET /api/config body", async () => {
    const config = { portfolio: { tickers: ["NVDA"], themes: [] } }
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => config,
    })
    const user = userEvent.setup()
    render(<ConfigFilePanel />)
    await user.click(screen.getByTestId("config-export"))
    await waitFor(() => {
      expect(screen.getByTestId("config-success")).toHaveTextContent("Exported")
    })
    expect(fetchMock).toHaveBeenCalledWith("/api/config", { cache: "no-store" })
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1)
  })

  it("Import: invalid JSON surfaces inline error and skips PUT", async () => {
    const user = userEvent.setup()
    render(<ConfigFilePanel />)
    const file = new File(["not json {{{"], "broken.json", {
      type: "application/json",
    })
    await user.upload(screen.getByTestId("config-import-input"), file)
    await waitFor(() => {
      expect(screen.getByTestId("config-error")).toHaveTextContent(
        /invalid json/i,
      )
    })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(refreshMock).not.toHaveBeenCalled()
  })

  it("Import: schema validation failure (422) surfaces inline error", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ detail: [] }),
    })
    const user = userEvent.setup()
    render(<ConfigFilePanel />)
    const file = new File(['{"portfolio": {}}'], "bad.json", {
      type: "application/json",
    })
    await user.upload(screen.getByTestId("config-import-input"), file)
    await waitFor(() => {
      expect(screen.getByTestId("config-error")).toHaveTextContent(
        /schema validation failed/i,
      )
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(refreshMock).not.toHaveBeenCalled()
  })

  it("Import: success path PUTs the parsed body and refreshes the router", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({}),
    })
    const user = userEvent.setup()
    render(<ConfigFilePanel />)
    const payload = { portfolio: { tickers: ["PLTR"], themes: [] } }
    const file = new File([JSON.stringify(payload)], "ok.json", {
      type: "application/json",
    })
    await user.upload(screen.getByTestId("config-import-input"), file)
    await waitFor(() => {
      expect(screen.getByTestId("config-success")).toHaveTextContent("Imported")
    })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe("/api/config")
    expect(init.method).toBe("PUT")
    expect(JSON.parse(String(init.body))).toEqual(payload)
    expect(refreshMock).toHaveBeenCalledTimes(1)
  })
})
