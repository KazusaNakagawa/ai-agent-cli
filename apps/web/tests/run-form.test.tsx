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
})
