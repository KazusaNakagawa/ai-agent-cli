import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { SetupPanel } from "@/components/settings/SetupPanel"

describe("SetupPanel", () => {
  const fetchMock = vi.fn()
  const assignMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    assignMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("location", { ...window.location, assign: assignMock })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("clears onboarded and opens the wizard in re-run mode", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ onboarded: false }), { status: 200 }),
    )
    const user = userEvent.setup()
    render(<SetupPanel />)

    await user.click(screen.getByTestId("rerun-setup"))

    await waitFor(() => expect(assignMock).toHaveBeenCalledWith("/?rerun=1"))
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/state",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ onboarded: false }),
      }),
    )
  })

  it("shows an error and stays put when PUT /api/state fails", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }))
    const user = userEvent.setup()
    render(<SetupPanel />)

    await user.click(screen.getByTestId("rerun-setup"))

    await waitFor(() => {
      expect(screen.getByTestId("rerun-setup-error")).toHaveTextContent(/500/)
    })
    expect(assignMock).not.toHaveBeenCalled()
    expect(screen.getByTestId("rerun-setup")).toBeEnabled()
  })
})
