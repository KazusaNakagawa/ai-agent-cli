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
})
