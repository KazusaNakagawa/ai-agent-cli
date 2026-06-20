import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { BriefingDashboard } from "@/components/screens/BriefingDashboard"

const FILES_RESPONSE = {
  files: [
    { name: "briefing_2026-06-20.md", type: "briefing", date: "2026-06-20", size: 512 },
    { name: "briefing_2026-06-19.md", type: "briefing", date: "2026-06-19", size: 256 },
    { name: "local_2026-06-18.md", type: "local", date: "2026-06-18", size: 128 },
  ],
}

const CONTENT_RESPONSE = {
  name: "briefing_2026-06-20.md",
  content: "# June 20 Briefing\n\nToday's market summary.",
}

const fetchMock = vi.fn()

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  })
}

describe("BriefingDashboard", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("shows loading state before files arrive", async () => {
    fetchMock.mockImplementation(() => new Promise<Response>(() => {}))
    render(<BriefingDashboard />)
    expect(screen.getByTestId("briefing-loading")).toBeInTheDocument()
  })

  it("renders file list as table rows", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument()
    })
    expect(screen.getByTestId("briefing-row-briefing_2026-06-20.md")).toBeInTheDocument()
    expect(screen.getByTestId("briefing-row-briefing_2026-06-19.md")).toBeInTheDocument()
    expect(screen.getByTestId("briefing-row-local_2026-06-18.md")).toBeInTheDocument()
  })

  it("auto-selects and loads the first file on mount", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId("briefing-content")).toBeInTheDocument()
    })
    expect(screen.getByTestId("briefing-content")).toHaveTextContent("June 20 Briefing")
  })

  it("loads content when a different row is clicked", async () => {
    const otherContent = { name: "briefing_2026-06-19.md", content: "# June 19 Briefing" }
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("briefing_2026-06-19")) return Promise.resolve(jsonResponse(otherContent))
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-row-briefing_2026-06-19.md"))

    await waitFor(() => {
      expect(screen.getByTestId("briefing-content")).toHaveTextContent("June 19 Briefing")
    })
  })

  it("renders markdown content (headings, text)", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)

    await waitFor(() => {
      const content = screen.getByTestId("briefing-content")
      expect(content.querySelector("h1")).toBeTruthy()
      expect(content).toHaveTextContent("Today's market summary.")
    })
  })

  it("shows empty state when no files are returned", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ files: [] }))
    render(<BriefingDashboard />)
    await waitFor(() => {
      expect(screen.getByTestId("briefing-empty")).toBeInTheDocument()
    })
  })

  it("shows error state when the list fetch fails", async () => {
    fetchMock.mockRejectedValue(new Error("Network error"))
    render(<BriefingDashboard />)
    await waitFor(() => {
      expect(screen.getByTestId("briefing-error")).toBeInTheDocument()
    })
  })
})
