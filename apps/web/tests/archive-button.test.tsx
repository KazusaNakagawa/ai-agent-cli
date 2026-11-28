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

  it("POSTs to /api/archive and shows the summary message", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ exit_code: 0, stdout: "raw", status: "archived", message: "Archived 2026-05 (35 files)" }),
    )
    render(<ArchiveButton />)

    await userEvent.setup().click(screen.getByTestId("archive-button"))

    await waitFor(() =>
      expect(screen.getByTestId("archive-message")).toHaveTextContent("Archived 2026-05 (35 files)"),
    )
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe("/api/archive")
    expect(opts.method).toBe("POST")
  })

  it("does not render the raw script output or paths", async () => {
    const stdout = [
      "  adding: briefing_2026-05-01.md (deflated 61%)",
      "created: /Users/me/out/briefing_2026-05.zip (1 files)",
      "uploaded: gdrive:ai-agent/briefing/briefing_2026-05.zip",
    ].join("\n")
    fetchMock.mockResolvedValue(
      jsonResponse({ exit_code: 0, stdout, status: "archived", message: "Archived 2026-05 (1 file)" }),
    )
    render(<ArchiveButton />)

    await userEvent.setup().click(screen.getByTestId("archive-button"))

    const toast = await screen.findByTestId("archive-message")
    expect(toast).toHaveTextContent("Archived 2026-05 (1 file)")
    for (const noise of ["adding:", "deflated", "/Users/me", "gdrive:"]) {
      expect(toast).not.toHaveTextContent(noise)
    }
  })

  it("shows the nothing-to-archive message as a success", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        exit_code: 0,
        stdout: "skip: ...",
        status: "skipped",
        message: "Nothing to archive for 2026-04: no briefing files.",
      }),
    )
    render(<ArchiveButton />)

    await userEvent.setup().click(screen.getByTestId("archive-button"))

    await waitFor(() =>
      expect(screen.getByTestId("archive-message")).toHaveTextContent("Nothing to archive for 2026-04"),
    )
  })

  it("falls back to a generic message when the API sends no summary", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ exit_code: 0, stdout: "adding: x (stored 0%)" }))
    render(<ArchiveButton />)

    await userEvent.setup().click(screen.getByTestId("archive-button"))

    const toast = await screen.findByTestId("archive-message")
    expect(toast).toHaveTextContent("Archive complete.")
    expect(toast).not.toHaveTextContent("adding:")
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
    fetchMock.mockResolvedValue(
      jsonResponse({ exit_code: 0, stdout: "raw", status: "archived", message: "Archived 2026-05 (35 files)" }),
    )
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
