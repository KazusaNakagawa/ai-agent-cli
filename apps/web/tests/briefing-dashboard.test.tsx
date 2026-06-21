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
    // Reset the ?type= URL so tab state does not leak across tests.
    window.history.replaceState(null, "", "/")
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

  it("opens side panel when the row itself is clicked", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/")) return Promise.resolve(jsonResponse(CONTENT_RESPONSE))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-row-briefing_2026-06-20.md"))

    await waitFor(() => expect(screen.getByTestId("briefing-panel")).toBeInTheDocument())
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
    // type shows the mapped label, not the raw enum
    expect(screen.getByTestId("panel-type")).toHaveTextContent("Briefing")
    expect(screen.getByTestId("panel-date")).toHaveTextContent("2026-06-20")
    // 5120 bytes formats to "5.0 KB"
    expect(screen.getByTestId("panel-size")).toHaveTextContent("5.0 KB")
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

    const recordsList = screen.getByTestId("briefing-records-list")
    expect(recordsList).not.toHaveClass("hidden")

    const fullSizeBtn = screen.getByTestId("panel-fullsize-btn")

    // Expand: records list is hidden, panel stays mounted
    await user.click(fullSizeBtn)
    await waitFor(() => expect(screen.getByTestId("briefing-records-list")).toHaveClass("hidden"))
    expect(screen.getByTestId("briefing-panel")).toBeInTheDocument()

    // Collapse: records list visible again
    await user.click(screen.getByTestId("panel-fullsize-btn"))
    await waitFor(() => expect(screen.getByTestId("briefing-records-list")).not.toHaveClass("hidden"))
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

  it("renders a Type tab per type present and filters the list on select", async () => {
    fetchMock.mockResolvedValue(jsonResponse(FILES_RESPONSE))
    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    expect(screen.getByTestId("briefing-tab-all")).toBeInTheDocument()
    expect(screen.getByTestId("briefing-tab-briefing")).toBeInTheDocument()
    expect(screen.getByTestId("briefing-tab-local")).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-tab-local"))

    // local-only after filtering
    expect(screen.getByTestId("briefing-row-local_2026-06-18.md")).toBeInTheDocument()
    expect(screen.queryByTestId("briefing-row-briefing_2026-06-20.md")).not.toBeInTheDocument()

    // All restores everything
    await user.click(screen.getByTestId("briefing-tab-all"))
    expect(screen.getByTestId("briefing-row-briefing_2026-06-20.md")).toBeInTheDocument()
  })

  it("persists the selected tab to the ?type= URL query", async () => {
    fetchMock.mockResolvedValue(jsonResponse(FILES_RESPONSE))
    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByTestId("briefing-tab-local"))
    expect(new URLSearchParams(window.location.search).get("type")).toBe("local")

    await user.click(screen.getByTestId("briefing-tab-all"))
    expect(new URLSearchParams(window.location.search).get("type")).toBeNull()
  })

  it("restores the selected tab from ?type= on load", async () => {
    window.history.replaceState(null, "", "/?type=local")
    fetchMock.mockResolvedValue(jsonResponse(FILES_RESPONSE))
    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    expect(screen.getByTestId("briefing-row-local_2026-06-18.md")).toBeInTheDocument()
    expect(screen.queryByTestId("briefing-row-briefing_2026-06-20.md")).not.toBeInTheDocument()
    window.history.replaceState(null, "", "/")
  })

  it("filters via server search and combines with the Type tab (AND)", async () => {
    const searchResponse = {
      files: [
        { name: "briefing_2026-06-20.md", type: "briefing", date: "2026-06-20", size: 5120 },
        { name: "local_2026-06-18.md", type: "local", date: "2026-06-18", size: 1280 },
      ],
    }
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/search")) return Promise.resolve(jsonResponse(searchResponse))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.type(screen.getByTestId("briefing-search-input"), "content")

    // search narrows the list to the two server matches
    await waitFor(() =>
      expect(screen.queryByTestId("briefing-row-briefing_2026-06-19.md")).not.toBeInTheDocument(),
    )
    expect(screen.getByTestId("briefing-row-briefing_2026-06-20.md")).toBeInTheDocument()
    expect(screen.getByTestId("briefing-row-local_2026-06-18.md")).toBeInTheDocument()
    const searchUrl = fetchMock.mock.calls.map((c) => c[0]).find((u: string) => u.includes("/search"))
    expect(searchUrl).toContain("q=content")

    // AND with Type tab: local-only among the search matches
    await user.click(screen.getByTestId("briefing-tab-local"))
    expect(screen.getByTestId("briefing-row-local_2026-06-18.md")).toBeInTheDocument()
    expect(screen.queryByTestId("briefing-row-briefing_2026-06-20.md")).not.toBeInTheDocument()
  })

  it("clearing the search returns to tab-only filtering", async () => {
    const searchResponse = {
      files: [{ name: "local_2026-06-18.md", type: "local", date: "2026-06-18", size: 1280 }],
    }
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/search")) return Promise.resolve(jsonResponse(searchResponse))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.type(screen.getByTestId("briefing-search-input"), "local")
    await waitFor(() =>
      expect(screen.queryByTestId("briefing-row-briefing_2026-06-20.md")).not.toBeInTheDocument(),
    )

    await user.click(screen.getByTestId("briefing-search-clear"))
    await waitFor(() =>
      expect(screen.getByTestId("briefing-row-briefing_2026-06-20.md")).toBeInTheDocument(),
    )
  })

  it("shows a zero-result state when the search has no matches", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/api/briefing/search")) return Promise.resolve(jsonResponse({ files: [] }))
      return Promise.resolve(jsonResponse(FILES_RESPONSE))
    })

    render(<BriefingDashboard />)
    await waitFor(() => expect(screen.getByTestId("briefing-dashboard")).toBeInTheDocument())

    const user = userEvent.setup()
    await user.type(screen.getByTestId("briefing-search-input"), "zzz")
    await waitFor(() => expect(screen.getByTestId("briefing-no-results")).toBeInTheDocument())
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
