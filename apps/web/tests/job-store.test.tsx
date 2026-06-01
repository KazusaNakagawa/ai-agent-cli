import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Sidebar } from "@/components/Sidebar"
import { RunForm } from "@/components/screens/RunForm"
import { JobStateProvider } from "@/lib/jobStore"

vi.mock("next/navigation", () => ({
  usePathname: () => "/portfolio",
}))

const STORAGE_KEY = "ai-agent:run-job:v1"

function seedStoredJob(state: Record<string, unknown>): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

describe("JobStateProvider — resume from sessionStorage", () => {
  const fetchMock = vi.fn()
  let realSetTimeout: typeof setTimeout

  beforeEach(() => {
    sessionStorage.clear()
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    realSetTimeout = global.setTimeout
    vi.stubGlobal(
      "setTimeout",
      ((cb: (...a: unknown[]) => void) =>
        realSetTimeout(cb, 0)) as unknown as typeof setTimeout,
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it("resumes polling when mounted with a stored running job (AC: page reload mid-flight)", async () => {
    seedStoredJob({
      jobId: "resume-1",
      status: "running",
      dryRun: false,
      startedAt: "2026-05-31T12:00:00Z",
      finishedAt: null,
      error: null,
    })
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          job_id: "resume-1",
          status: "done",
          finished_at: "2026-05-31T12:05:00Z",
        }),
        { status: 200 },
      ),
    )

    render(
      <JobStateProvider>
        <RunForm />
      </JobStateProvider>,
    )

    // Status is restored from sessionStorage even before the first poll lands.
    await waitFor(() => {
      expect(screen.getByTestId("job-status")).toHaveTextContent(/running|done/)
    })
    await waitFor(() => {
      expect(screen.getByTestId("job-status")).toHaveTextContent("done")
    })
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/run/resume-1",
      expect.objectContaining({ cache: "no-store" }),
    )
  })

  it("does not poll when mounted with a stored terminal job (AC: no polling for done jobs)", async () => {
    seedStoredJob({
      jobId: "resume-done",
      status: "done",
      dryRun: false,
      startedAt: "2026-05-31T12:00:00Z",
      finishedAt: "2026-05-31T12:05:00Z",
      error: null,
    })

    render(
      <JobStateProvider>
        <RunForm />
      </JobStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("job-status")).toHaveTextContent("done")
    })
    // Give the loop a chance to run if it were going to.
    await new Promise((r) => realSetTimeout(r, 20))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("clears state with an informative message when the backend returns 404 on resume", async () => {
    seedStoredJob({
      jobId: "gone-job",
      status: "running",
      dryRun: false,
      startedAt: "2026-05-31T12:00:00Z",
      finishedAt: null,
      error: null,
    })
    fetchMock.mockResolvedValueOnce(new Response("not found", { status: 404 }))

    render(
      <JobStateProvider>
        <RunForm />
      </JobStateProvider>,
    )

    // First confirm the seeded job hydrated.
    await waitFor(() => {
      expect(screen.getByTestId("job-status")).toHaveTextContent("running")
    })
    await waitFor(
      () => {
        expect(screen.getByTestId("run-error")).toBeInTheDocument()
      },
      { timeout: 3000, interval: 25 },
    )
    // Job card cleared (no more jobId), only the error remains.
    expect(screen.queryByTestId("job-status")).toBeNull()
    expect(screen.queryByText(/gone-job/)).toBeNull()
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeTruthy() // error state persisted
  })

  it("drops an unresumable persisted snapshot (status=pending, jobId=null)", async () => {
    // Simulates a reload during the brief window where startJob() has flipped
    // status to "pending" but the POST has not yet returned a job_id.
    seedStoredJob({
      jobId: null,
      status: "pending",
      dryRun: false,
      startedAt: null,
      finishedAt: null,
      error: null,
    })

    render(
      <JobStateProvider>
        <RunForm />
      </JobStateProvider>,
    )

    // No job card (no jobId), Run button enabled (status normalized to idle).
    await waitFor(() => {
      expect(screen.getByTestId("run-button")).not.toBeDisabled()
    })
    expect(screen.queryByTestId("job-status")).toBeNull()
    // Nothing in flight → no poll fetched.
    await new Promise((r) => realSetTimeout(r, 20))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("restores the dry-run checkbox to match the persisted job's mode", async () => {
    seedStoredJob({
      jobId: "dry-job",
      status: "done",
      dryRun: true,
      startedAt: "2026-05-31T12:00:00Z",
      finishedAt: "2026-05-31T12:05:00Z",
      error: null,
    })

    render(
      <JobStateProvider>
        <RunForm />
      </JobStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("dry-run-checkbox")).toBeChecked()
    })
    // Badge on the restored job card confirms dryRun made it through hydration.
    expect(screen.getByText("dry_run")).toBeInTheDocument()
  })

  it("shows the sidebar dot on /run while a background job is in flight", async () => {
    seedStoredJob({
      jobId: "bg-job",
      status: "running",
      dryRun: false,
      startedAt: "2026-05-31T12:00:00Z",
      finishedAt: null,
      error: null,
    })
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ job_id: "bg-job", status: "running" }),
        { status: 200 },
      ),
    )

    render(
      <JobStateProvider>
        <Sidebar />
      </JobStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("sidebar-run-dot")).toBeInTheDocument()
    })
    // Dot is anchored on the Run nav row.
    const runLink = screen.getByTestId("nav-run")
    expect(runLink).toContainElement(screen.getByTestId("sidebar-run-dot"))
  })
})
