import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChatSplitView } from "@/components/screens/ChatSplitView"

// The Q&A pane is exercised by tests/chat-form.test.tsx. Stubbing it here keeps
// this suite about the split layout and avoids pulling the chat providers,
// SSE plumbing, and the mount-time /api/credentials fetch into every case.
vi.mock("@/components/screens/ChatForm", () => ({
  ChatForm: () => <div data-testid="chat-form-stub" />,
}))

const FILES_RESPONSE = {
  files: [
    { name: "briefing_2026-08-01.md", type: "briefing", date: "2026-08-01", size: 25800 },
    { name: "briefing_2026-07-31.md", type: "briefing", date: "2026-07-31", size: 5120 },
    { name: "local_2026-07-30.md", type: "local", date: "2026-07-30", size: 1280 },
  ],
}

const WIDTH_KEY = "ai-agent:chat-split-width:v1"
const DEFAULT_WIDTH = 480

const fetchMock = vi.fn()

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  })
}

/** Route each request by URL so list and content responses can't be swapped. */
function routeFetch(contents: Record<string, string> = {}) {
  fetchMock.mockImplementation((url: string) => {
    if (url === "/api/briefing") return Promise.resolve(jsonResponse(FILES_RESPONSE))
    const name = decodeURIComponent(url.replace("/api/briefing/", ""))
    const content = contents[name]
    if (content === undefined) {
      return Promise.resolve(new Response("not found", { status: 404 }))
    }
    return Promise.resolve(jsonResponse({ name, content }))
  })
}

describe("ChatSplitView", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it("renders the Q&A pane on the left and the document pane on the right", async () => {
    routeFetch({ "briefing_2026-08-01.md": "# Aug 1\n\nToday's summary." })
    render(<ChatSplitView />)

    const root = await screen.findByTestId("chat-split-view")
    const qa = screen.getByTestId("chat-pane-qa")
    const doc = await screen.findByTestId("chat-pane-doc")

    expect(within(qa).getByTestId("chat-form-stub")).toBeInTheDocument()
    // Document order inside the split container decides which pane is left.
    const panes = Array.from(root.children)
    expect(panes.indexOf(qa)).toBeLessThan(panes.indexOf(doc))
  })

  it("auto-opens the newest briefing and renders its markdown", async () => {
    routeFetch({ "briefing_2026-08-01.md": "# Aug 1\n\nToday's summary." })
    render(<ChatSplitView />)

    expect(await screen.findByTestId("briefing-content")).toHaveTextContent("Today's summary.")
    expect(screen.getByTestId("panel-title")).toHaveTextContent("briefing_2026-08-01.md")
  })

  it("switches the document when another file is picked", async () => {
    routeFetch({
      "briefing_2026-08-01.md": "# Aug 1\n\nToday's summary.",
      "local_2026-07-30.md": "# Jul 30\n\nLocal notes.",
    })
    render(<ChatSplitView />)
    await screen.findByTestId("briefing-content")

    await userEvent.selectOptions(
      screen.getByTestId("chat-doc-picker"),
      "local_2026-07-30.md",
    )

    await waitFor(() => {
      expect(screen.getByTestId("briefing-content")).toHaveTextContent("Local notes.")
    })
    expect(screen.getByTestId("panel-title")).toHaveTextContent("local_2026-07-30.md")
  })

  it("shows an empty state instead of a blank pane when no files exist", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ files: [] }))
    render(<ChatSplitView />)

    expect(await screen.findByTestId("chat-doc-empty")).toBeInTheDocument()
    expect(screen.queryByTestId("chat-doc-picker")).not.toBeInTheDocument()
    expect(screen.queryByTestId("briefing-panel")).not.toBeInTheDocument()
  })

  it("surfaces a list fetch failure in the document pane", async () => {
    fetchMock.mockResolvedValue(new Response("boom", { status: 500 }))
    render(<ChatSplitView />)

    expect(await screen.findByTestId("chat-doc-error")).toHaveTextContent("500")
  })

  it("surfaces a content fetch failure without losing the pane", async () => {
    // List resolves but the newest file's body 404s.
    routeFetch({})
    render(<ChatSplitView />)

    expect(await screen.findByTestId("briefing-content-error")).toBeInTheDocument()
    expect(screen.getByTestId("chat-pane-qa")).toBeInTheDocument()
  })

  it("restores a persisted pane width and ignores an out-of-range one", async () => {
    localStorage.setItem(WIDTH_KEY, "640")
    routeFetch({ "briefing_2026-08-01.md": "# Aug 1" })
    const { unmount } = render(<ChatSplitView />)
    await waitFor(() => {
      expect(screen.getByTestId("chat-pane-doc").style.getPropertyValue("--doc-width")).toBe(
        "640px",
      )
    })
    unmount()

    localStorage.setItem(WIDTH_KEY, "99999")
    render(<ChatSplitView />)
    const doc = await screen.findByTestId("chat-pane-doc")
    expect(doc.style.getPropertyValue("--doc-width")).toBe(`${DEFAULT_WIDTH}px`)
  })

  it("exposes a resize handle between the two panes", async () => {
    routeFetch({ "briefing_2026-08-01.md": "# Aug 1" })
    render(<ChatSplitView />)
    expect(await screen.findByTestId("chat-split-resizer")).toBeInTheDocument()
  })

  it("toggles which pane is visible on narrow viewports", async () => {
    routeFetch({ "briefing_2026-08-01.md": "# Aug 1" })
    render(<ChatSplitView />)
    await screen.findByTestId("briefing-content")

    // Narrow default: Q&A visible, document hidden until lg.
    expect(screen.getByTestId("chat-pane-doc").className).toContain("hidden")
    expect(screen.getByTestId("chat-pane-qa").className).not.toContain("hidden")

    await userEvent.click(screen.getByTestId("chat-doc-toggle"))

    expect(screen.getByTestId("chat-pane-doc").className).not.toContain("hidden")
    expect(screen.getByTestId("chat-pane-qa").className).toContain("hidden")
  })
})
