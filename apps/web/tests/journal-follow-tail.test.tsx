import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { JournalSidebarList } from "@/components/journal/JournalSidebarList"
import { JournalScreen } from "@/components/screens/JournalScreen"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"
import { JournalNavProvider } from "@/lib/journalNavStore"

// The entry list only loads on the journal route.
vi.mock("next/navigation", () => ({ usePathname: () => "/journal" }))

const ENTRY = { id: "2026-11-07_101500", date: "2026-11-07", size: 10, item: "Demo entry", notion_url: "" }
const HEIGHT = 5000

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

function renderJournal() {
  render(
    <JournalChatStateProvider>
      <JournalChatJobStateProvider>
        <JournalNavProvider>
          <JournalSidebarList />
          <JournalScreen />
        </JournalNavProvider>
      </JournalChatJobStateProvider>
    </JournalChatStateProvider>,
  )
}

// jsdom has no layout; give the panel's scroll area a tall content height.
function tallScrollArea() {
  const area = screen.getByTestId("journal-scroll")
  Object.defineProperty(area, "clientHeight", { configurable: true, value: 500 })
  Object.defineProperty(area, "scrollHeight", { configurable: true, value: HEIGHT })
  return area
}

describe("journal follows a brainstorm", () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    window.sessionStorage.clear()
    vi.stubGlobal("fetch", fetchMock)
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? "GET"
      if (url === "/api/journal" && method === "GET") return jsonResponse({ entries: [ENTRY] })
      if (url === `/api/journal/${ENTRY.id}` && method === "GET") {
        return jsonResponse({ content: "# Journal 2026-11-07\n\nA long entry." })
      }
      if (url === "/api/journal/chat") return jsonResponse({ job_id: "f-1" }, 202)
      if (url === "/api/chat/f-1/stream") return new Promise<Response>(() => {})
      return jsonResponse({}, 404)
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    window.sessionStorage.clear()
  })

  it("opens an entry at the top instead of jumping to the end", async () => {
    renderJournal()
    fireEvent.click(await screen.findByText("Demo entry"))
    const area = tallScrollArea()
    await screen.findByText("A long entry.")
    expect(area.scrollTop).toBe(0)
  })

  it("moves to the end once a brainstorm is sent", async () => {
    renderJournal()
    fireEvent.click(await screen.findByText("Demo entry"))
    const area = tallScrollArea()
    await screen.findByText("A long entry.")
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "ideas?" } })
    fireEvent.click(screen.getByRole("button", { name: "Brainstorm" }))
    await waitFor(() => expect(area.scrollTop).toBe(HEIGHT))
  })
})
