import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { BriefingDashboard } from "@/components/screens/BriefingDashboard"


const FILES_RESPONSE = {
  files: [
    { name: "briefing_2026-06-20.md", type: "briefing", date: "2026-06-20", size: 5120 },
    { name: "briefing_2026-06-19.md", type: "briefing", date: "2026-06-19", size: 2560 },
    { name: "local_2026-06-18.md", type: "local", date: "2026-06-18", size: 1280 },
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

  it("renders file list as table rows without auto-opening panel", async () => {
    fetchMock.mockResolvedValue(jsonResponse(FILES_RESPONSE))
    render(<BriefingDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument()
    })
    expect(screen.getByTestId("briefing-row-briefing_2026-06-20.md")).toBeInTheDocument()
    expect(screen.getByTestId("briefing-row-briefing_2026-06-19.md")).toBeInTheDocument()
    expect(screen.getByTestId("briefing-row-local_2026-06-18.md")).toBeInTheDocument()
    expect(screen.queryByTestId("briefing-panel")).not.toBeInTheDocument()
  })

  it("opens side panel when the open icon is clicked", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-open-briefing_2026-06-20.md"))

    await waitFor(() => {
      expect(screen.getByTestId("briefing-panel")).toBeInTheDocument()
    })
    expect(screen.getByTestId("briefing-content")).toHaveTextContent("June 20 Briefing")
  })

  it("shows properties (type, date, size) in the panel header", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-open-briefing_2026-06-20.md"))

    await waitFor(() => expect(screen.getByTestId("briefing-panel")).toBeInTheDocument())
    expect(screen.getByTestId("panel-date")).toHaveTextContent("2026-06-20")
    expect(screen.getByTestId("panel-size")).toBeInTheDocument()
  })

  it("closes the panel when the close button is clicked", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-open-briefing_2026-06-20.md"))
    await waitFor(() => expect(screen.getByTestId("briefing-panel")).toBeInTheDocument())

    await user.click(screen.getByTestId("panel-close-btn"))
    expect(screen.queryByTestId("briefing-panel")).not.toBeInTheDocument()
  })

  it("toggles full-size view", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-open-briefing_2026-06-20.md"))
    await waitFor(() => expect(screen.getByTestId("briefing-panel")).toBeInTheDocument())

    const fullSizeBtn = screen.getByTestId("panel-fullsize-btn")
    await user.click(fullSizeBtn)
    // Full-size renders panel inside an absolute grid overlay (sidebar stays visible)
    expect(screen.getByTestId("briefing-panel")).toBeInTheDocument()
  })

  it("renders markdown content in the panel", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-open-briefing_2026-06-20.md"))

    await waitFor(() => {
      const content = screen.getByTestId("briefing-content")
      const h1 = content.querySelector("h1")
      expect(h1).toBeTruthy()
      // rehypeHeadingIds must attach a slug id that survives sanitization
      expect(h1?.getAttribute("id")).toBe("june-20-briefing")
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

  it("shows content error inline without hiding the file list", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/briefing") return Promise.resolve(jsonResponse(FILES_RESPONSE))
      return Promise.reject(new Error("content fetch failed"))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-open-briefing_2026-06-20.md"))

    await waitFor(() => {
      expect(screen.getByTestId("briefing-content-error")).toBeInTheDocument()
    })
    expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument()
  })

  it("activates row on Enter key press", async () => {
    const otherContent = { name: "briefing_2026-06-19.md", content: "# June 19 via keyboard" }
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("briefing_2026-06-19")) return Promise.resolve(jsonResponse(otherContent))
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    const row = screen.getByTestId("briefing-row-briefing_2026-06-19.md")
    await user.type(row, "{Enter}")

    await waitFor(() => {
      expect(screen.getByTestId("briefing-panel")).toBeInTheDocument()
      expect(screen.getByTestId("briefing-content")).toHaveTextContent("June 19 via keyboard")
    })
  })
})

describe("TOC navigation", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
  })

  it("gives Japanese headings ids that match the TOC slugs and scrolls on click", async () => {
    const jp = {
      name: "briefing_2026-06-20.md",
      content: "## 今日のサマリー（1文）\n\n本文A\n\n## なぜ動いたか（ストーリー）\n\n本文B",
    }
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(jp))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })
    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())
    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-open-briefing_2026-06-20.md"))

    let h2s: HTMLElement[] = []
    await waitFor(() => {
      const content = screen.getByTestId("briefing-content")
      h2s = Array.from(content.querySelectorAll("h2")) as HTMLElement[]
      // ids must NOT carry sanitize's "user-content-" prefix, so they match extractToc slugs
      expect(h2s.map((h) => h.getAttribute("id"))).toEqual([
        "今日のサマリー1文",
        "なぜ動いたかストーリー",
      ])
    })

    // scrollIntoView is the scroll mechanism; jsdom doesn't implement it
    const scrollIntoView = vi.fn()
    h2s[1].scrollIntoView = scrollIntoView

    await user.click(screen.getByTestId("panel-toc-btn"))
    const target = screen
      .getAllByRole("button")
      .find((b) => b.textContent === "なぜ動いたか（ストーリー）") as HTMLElement
    await user.click(target)

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" })
    // clicking a TOC entry closes the TOC
    expect(screen.queryByTestId("briefing-toc")?.closest(".opacity-0")).toBeTruthy()
  })
})
