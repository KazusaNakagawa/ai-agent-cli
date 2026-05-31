import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { CredentialsForm } from "@/components/screens/CredentialsForm"

// next/navigation is opaque under jsdom; stub the bits the component touches.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

describe("CredentialsForm", () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const initial = {
    DISCORD_TOKEN: true,
    CHANNEL_ID: false,
    NOTION_API_KEY: false,
    NOTION_DATABASE_ID: true,
    ANTHROPIC_API_KEY: false,
  }

  it("renders Set / Not set badges from status", () => {
    render(<CredentialsForm initial={initial} />)
    expect(screen.getByTestId("status-DISCORD_TOKEN")).toHaveTextContent("Set")
    expect(screen.getByTestId("status-CHANNEL_ID")).toHaveTextContent("Not set")
    expect(screen.getByTestId("status-NOTION_DATABASE_ID")).toHaveTextContent(
      "Set",
    )
  })

  it("PUTs masked value when the dialog Save is clicked", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    const user = userEvent.setup()
    render(<CredentialsForm initial={initial} />)

    await user.click(screen.getByTestId("update-ANTHROPIC_API_KEY"))
    const input = (await screen.findByTestId(
      "credential-draft",
    )) as HTMLInputElement
    expect(input.type).toBe("password") // secret field is masked

    await user.type(input, "sk-test-key")
    await user.click(screen.getByTestId("credential-save"))

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/credentials/ANTHROPIC_API_KEY",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ value: "sk-test-key" }),
      }),
    )
    await waitFor(() => {
      expect(screen.getByTestId("status-ANTHROPIC_API_KEY")).toHaveTextContent(
        "Set",
      )
    })
  })

  it("renders the Channel ID input as text (not a password)", async () => {
    const user = userEvent.setup()
    render(<CredentialsForm initial={initial} />)
    await user.click(screen.getByTestId("update-CHANNEL_ID"))
    const input = (await screen.findByTestId(
      "credential-draft",
    )) as HTMLInputElement
    expect(input.type).toBe("text")
  })

  it("DELETEs the credential and flips the badge to Not set", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    const user = userEvent.setup()
    render(<CredentialsForm initial={initial} />)

    await user.click(screen.getByTestId("delete-DISCORD_TOKEN"))

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/credentials/DISCORD_TOKEN",
      expect.objectContaining({ method: "DELETE" }),
    )
    await waitFor(() => {
      expect(screen.getByTestId("status-DISCORD_TOKEN")).toHaveTextContent(
        "Not set",
      )
    })
  })

  it("disables Delete when the credential is not set", () => {
    render(<CredentialsForm initial={initial} />)
    const btn = screen.getByTestId("delete-CHANNEL_ID") as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })

  it("does not PUT when the draft is empty", async () => {
    const user = userEvent.setup()
    render(<CredentialsForm initial={initial} />)
    await user.click(screen.getByTestId("update-ANTHROPIC_API_KEY"))
    await user.click(screen.getByTestId("credential-save"))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByTestId("credential-error")).toHaveTextContent(
      /required/i,
    )
  })
})
