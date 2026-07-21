import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ArchiveButton } from "@/components/briefing/ArchiveButton"

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

describe("ArchiveButton", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("POSTs to /api/archive and shows the result", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ exit_code: 0, stdout: "created: briefing_2026-05.zip" }))
    render(<ArchiveButton />)

    await userEvent.setup().click(screen.getByTestId("archive-button"))

    await waitFor(() =>
      expect(screen.getByTestId("archive-message")).toHaveTextContent("briefing_2026-05.zip"),
    )
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe("/api/archive")
    expect(opts.method).toBe("POST")
  })

  it("surfaces the error detail on failure", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "archive failed: rclone not found" }, 500))
    render(<ArchiveButton />)

    await userEvent.setup().click(screen.getByTestId("archive-button"))

    await waitFor(() =>
      expect(screen.getByTestId("archive-message")).toHaveTextContent("rclone not found"),
    )
  })

  it("dismisses the toast when the close button is clicked", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ exit_code: 0, stdout: "created: briefing_2026-05.zip" }))
    render(<ArchiveButton />)
    const user = userEvent.setup()

    await user.click(screen.getByTestId("archive-button"))
    await waitFor(() => expect(screen.getByTestId("archive-message")).toBeInTheDocument())

    await user.click(screen.getByTestId("toast-close"))

    await waitFor(() =>
      expect(screen.queryByTestId("archive-message")).not.toBeInTheDocument(),
    )
  })
})
