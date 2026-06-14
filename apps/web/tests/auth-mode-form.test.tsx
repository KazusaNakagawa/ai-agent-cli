import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AuthModeForm } from "@/components/screens/AuthModeForm"

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

describe("AuthModeForm", () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("blocks API mode selection when ANTHROPIC_API_KEY is not set", async () => {
    const user = userEvent.setup()
    render(<AuthModeForm initialAuthMode="cli" anthropicKeySet={false} />)
    await user.click(screen.getByTestId("auth-radio-api"))
    expect(screen.getByTestId("api-blocked")).toBeInTheDocument()

    await user.click(screen.getByTestId("auth-save"))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("allows API mode selection when ANTHROPIC_API_KEY is set", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ auth_mode: "api" }), { status: 200 }),
    )
    const user = userEvent.setup()
    render(<AuthModeForm initialAuthMode="cli" anthropicKeySet={true} />)
    await user.click(screen.getByTestId("auth-radio-api"))
    expect(screen.queryByTestId("api-blocked")).toBeNull()

    await user.click(screen.getByTestId("auth-save"))

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/mode",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ auth_mode: "api" }),
      }),
    )
    await waitFor(() => {
      expect(screen.getByTestId("save-status")).toHaveTextContent("Saved")
    })
  })

  it("disables Save when the current selection matches the initial mode", () => {
    render(<AuthModeForm initialAuthMode="cli" anthropicKeySet={true} />)
    const btn = screen.getByTestId("auth-save") as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})
