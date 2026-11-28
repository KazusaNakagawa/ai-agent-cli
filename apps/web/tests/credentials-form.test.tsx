import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { CredentialsForm } from "@/components/screens/CredentialsForm"

// next/navigation is opaque under jsdom; stub the bits the component touches.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

type Source = "keychain" | "env" | null

describe("CredentialsForm", () => {
  const fetchMock = vi.fn()
  // Mirrors what GET /api/credentials/sources would answer; PUT/DELETE update
  // it the way the backend would, so a post-mutation refetch stays consistent.
  let sources: Record<string, Source>
  let sourcesFail: boolean

  const initial = {
    DISCORD_TOKEN: true,
    CHANNEL_ID: false,
    NOTION_API_KEY: false,
    NOTION_DATABASE_ID: true,
    ANTHROPIC_API_KEY: false,
  }

  const writes = () =>
    fetchMock.mock.calls.filter(([url]) => url !== "/api/credentials/sources")

  beforeEach(() => {
    sourcesFail = false
    sources = Object.fromEntries(
      Object.entries(initial).map(([k, v]) => [k, v ? "keychain" : null]),
    )
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/credentials/sources") {
        if (sourcesFail) return new Response(null, { status: 500 })
        return Response.json(sources)
      }
      const name = decodeURIComponent(url.split("/").pop() ?? "")
      if (init?.method === "PUT") sources = { ...sources, [name]: "keychain" }
      if (init?.method === "DELETE") sources = { ...sources, [name]: null }
      return new Response(null, { status: 204 })
    })
    vi.stubGlobal("fetch", fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders Set / Not set badges from status", () => {
    render(<CredentialsForm initial={initial} />)
    expect(screen.getByTestId("status-DISCORD_TOKEN")).toHaveTextContent("Set")
    expect(screen.getByTestId("status-CHANNEL_ID")).toHaveTextContent("Not set")
    expect(screen.getByTestId("status-NOTION_DATABASE_ID")).toHaveTextContent(
      "Set",
    )
  })

  it("PUTs masked value when the dialog Save is clicked", async () => {
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
    expect(writes()).toEqual([])
    expect(screen.getByTestId("credential-error")).toHaveTextContent(
      /required/i,
    )
  })

  it("marks a key read from .env and disables its Delete", async () => {
    sources = { ...sources, NOTION_API_KEY: "env" }
    render(<CredentialsForm initial={initial} />)
    expect(await screen.findByTestId("source-env-NOTION_API_KEY")).toHaveTextContent(
      "From .env",
    )
    expect(screen.getByTestId("status-NOTION_API_KEY")).toHaveTextContent("Set")
    expect(
      (screen.getByTestId("delete-NOTION_API_KEY") as HTMLButtonElement).disabled,
    ).toBe(true)
    // Keychain-backed keys get no badge.
    expect(screen.queryByTestId("source-env-DISCORD_TOKEN")).toBeNull()
  })

  it("keeps a key Set after delete when .env still supplies it", async () => {
    const user = userEvent.setup()
    render(<CredentialsForm initial={initial} />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    // The keychain entry goes away but the environment still has a value.
    fetchMock.mockImplementationOnce(async () => {
      sources = { ...sources, DISCORD_TOKEN: "env" }
      return new Response(null, { status: 204 })
    })
    await user.click(screen.getByTestId("delete-DISCORD_TOKEN"))
    expect(await screen.findByTestId("source-env-DISCORD_TOKEN")).toBeInTheDocument()
    expect(screen.getByTestId("status-DISCORD_TOKEN")).toHaveTextContent("Set")
  })

  it("shows no source badge when the sources request fails", async () => {
    sourcesFail = true
    sources = { ...sources, NOTION_API_KEY: "env" }
    render(<CredentialsForm initial={initial} />)
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/credentials/sources",
        expect.anything(),
      ),
    )
    expect(screen.queryByTestId("source-env-NOTION_API_KEY")).toBeNull()
    // The server-rendered status stays as it was.
    expect(screen.getByTestId("status-DISCORD_TOKEN")).toHaveTextContent("Set")
  })

  it.each([
    ["PUT", "credential-error"],
    ["DELETE", "generic-error"],
  ])("shows the server's reason when %s fails", async (method, testId) => {
    const detail = "No OS keychain backend is available. Add the line to /home/x/.env"
    const user = userEvent.setup()
    render(<CredentialsForm initial={initial} />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    fetchMock.mockImplementationOnce(async () => Response.json({ detail }, { status: 503 }))

    if (method === "PUT") {
      await user.click(screen.getByTestId("update-CHANNEL_ID"))
      await user.type(await screen.findByTestId("credential-draft"), "123")
      await user.click(screen.getByTestId("credential-save"))
    } else {
      await user.click(screen.getByTestId("delete-DISCORD_TOKEN"))
    }

    expect(await screen.findByTestId(testId)).toHaveTextContent(detail)
  })

  it("falls back to the status code when the error body has no detail", async () => {
    const user = userEvent.setup()
    render(<CredentialsForm initial={initial} />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    fetchMock.mockImplementationOnce(async () => new Response("boom", { status: 500 }))
    await user.click(screen.getByTestId("delete-DISCORD_TOKEN"))
    expect(await screen.findByTestId("generic-error")).toHaveTextContent(
      "DELETE failed (HTTP 500)",
    )
  })
})
