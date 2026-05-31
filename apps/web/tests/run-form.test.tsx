import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { RunForm } from "@/components/screens/RunForm"

describe("RunForm", () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders idle with the Run button enabled", () => {
    render(<RunForm />)
    expect(screen.getByTestId("run-button")).not.toBeDisabled()
  })

  it("POSTs without dry_run by default", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ job_id: "abc-123", status: "pending" }),
        { status: 202 },
      ),
    )
    const user = userEvent.setup()
    render(<RunForm />)
    await user.click(screen.getByTestId("run-button"))
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/run",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("propagates ?dry_run=true when the checkbox is checked", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ job_id: "abc-123", status: "pending" }),
        { status: 202 },
      ),
    )
    const user = userEvent.setup()
    render(<RunForm />)
    await user.click(screen.getByTestId("dry-run-checkbox"))
    await user.click(screen.getByTestId("run-button"))
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/run?dry_run=true",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("disables the Run button while a job is in flight", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ job_id: "abc-123", status: "pending" }),
        { status: 202 },
      ),
    )
    const user = userEvent.setup()
    render(<RunForm />)
    await user.click(screen.getByTestId("run-button"))
    await waitFor(() => {
      expect(screen.getByTestId("run-button")).toBeDisabled()
    })
  })

  it("shows the session-expired card when POST returns 401", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 401 }))
    const user = userEvent.setup()
    render(<RunForm />)
    await user.click(screen.getByTestId("run-button"))
    await waitFor(() => {
      expect(screen.getByTestId("session-expired")).toBeInTheDocument()
    })
    // Run button is gone in the session-expired state.
    expect(screen.queryByTestId("run-button")).toBeNull()
  })

  it("renders the job card with job_id and a dry_run badge", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          job_id: "abc-123",
          status: "pending",
          dry_run: true,
        }),
        { status: 202 },
      ),
    )
    const user = userEvent.setup()
    render(<RunForm />)
    await user.click(screen.getByTestId("dry-run-checkbox"))
    await user.click(screen.getByTestId("run-button"))
    await waitFor(() => {
      expect(screen.getByTestId("job-status")).toHaveTextContent("pending")
    })
    expect(screen.getByText(/abc-123/)).toBeInTheDocument()
    expect(screen.getByText("dry_run")).toBeInTheDocument()
  })

  it("renders the error card when POST fails with non-401", async () => {
    fetchMock.mockResolvedValueOnce(new Response("oops", { status: 500 }))
    const user = userEvent.setup()
    render(<RunForm />)
    await user.click(screen.getByTestId("run-button"))
    await waitFor(() => {
      expect(screen.getByTestId("run-error")).toBeInTheDocument()
    })
    expect(screen.getByTestId("run-error")).toHaveTextContent("HTTP 500")
    // Button re-enables (status === "failed", not busy) so user can retry.
    expect(screen.getByTestId("run-button")).not.toBeDisabled()
  })

  describe("polling loop", () => {
    // Collapse the 2s poll delay to 0ms so the loop runs at microtask speed.
    // Keeping real timers everywhere else avoids the userEvent + fake-timer
    // entanglement and lets waitFor work normally.
    let realSetTimeout: typeof setTimeout
    beforeEach(() => {
      realSetTimeout = global.setTimeout
      vi.stubGlobal(
        "setTimeout",
        ((cb: (...a: unknown[]) => void) =>
          realSetTimeout(cb, 0)) as unknown as typeof setTimeout,
      )
    })

    it("polls pending → running → done and preserves dry_run badge", async () => {
      fetchMock
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              job_id: "abc-123",
              status: "pending",
              dry_run: true,
            }),
            { status: 202 },
          ),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ job_id: "abc-123", status: "running" }),
            { status: 200 },
          ),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              job_id: "abc-123",
              status: "done",
              finished_at: "2026-05-31T12:00:00Z",
            }),
            { status: 200 },
          ),
        )
      const user = userEvent.setup()
      render(<RunForm />)
      await user.click(screen.getByTestId("dry-run-checkbox"))
      await user.click(screen.getByTestId("run-button"))

      await waitFor(() => {
        expect(screen.getByTestId("job-status")).toHaveTextContent("done")
      })
      // dry_run came from the POST response; the GET responses omit it,
      // so this assertion proves the merge logic preserves the badge.
      expect(screen.getByText("dry_run")).toBeInTheDocument()
      expect(screen.getByTestId("finished-at")).toBeInTheDocument()
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/run/abc-123",
        expect.objectContaining({ cache: "no-store" }),
      )
    })

    it("surfaces a failed job with its error message", async () => {
      fetchMock
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ job_id: "abc-123", status: "pending" }),
            { status: 202 },
          ),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              job_id: "abc-123",
              status: "failed",
              error: "boom",
            }),
            { status: 200 },
          ),
        )
      const user = userEvent.setup()
      render(<RunForm />)
      await user.click(screen.getByTestId("run-button"))
      await waitFor(() => {
        expect(screen.getByTestId("job-status")).toHaveTextContent("failed")
      })
      expect(screen.getByTestId("run-error")).toHaveTextContent("boom")
    })

    it("shows session-expired when a poll returns 401", async () => {
      fetchMock
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ job_id: "abc-123", status: "pending" }),
            { status: 202 },
          ),
        )
        .mockResolvedValueOnce(new Response("", { status: 401 }))
      const user = userEvent.setup()
      render(<RunForm />)
      await user.click(screen.getByTestId("run-button"))
      await waitFor(() => {
        expect(screen.getByTestId("session-expired")).toBeInTheDocument()
      })
    })
  })
})
