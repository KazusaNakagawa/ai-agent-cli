import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { JournalScreen } from "@/components/screens/JournalScreen"
import { JournalSidebarList } from "@/components/journal/JournalSidebarList"
import { JournalChatBridge } from "@/components/journal/JournalChatBridge"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"
import { JournalNavProvider } from "@/lib/journalNavStore"

vi.mock("next/navigation", () => ({ usePathname: () => "/journal" }))

type Handler = (init?: RequestInit) => Promise<Response> | Response

function sseStream(parts: { data: string }[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const p of parts) controller.enqueue(encoder.encode(`data: ${p.data}\n\n`))
      controller.close()
    },
  })
  return new Response(stream, { status: 200 })
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

// Renders the same provider tree app/(main)/layout.tsx does, so unmounting
// just <JournalScreen /> (simulating navigating to another page) leaves the
// job/bridge running, exactly like the real layout.
function Shell({ showJournal }: { showJournal: boolean }) {
  return (
    <JournalChatStateProvider>
      <JournalChatJobStateProvider>
        <JournalNavProvider>
          <JournalChatBridge />
          {showJournal && (
            <>
              <JournalSidebarList />
              <JournalScreen />
            </>
          )}
        </JournalNavProvider>
      </JournalChatJobStateProvider>
    </JournalChatStateProvider>
  )
}

describe("Journal chat survives navigation away and back", () => {
  const fetchMock = vi.fn()
  let queues: Record<string, Handler[]>

  function on(url: string, handler: Handler) {
    if (!queues[url]) queues[url] = []
    queues[url].push(handler)
  }

  beforeEach(() => {
    queues = {}
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (url: string | URL, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      const queue = queues[u]
      if (queue && queue.length > 0) {
        const handler = queue.shift()!
        return await handler(init)
      }
      throw new Error(`Unmocked fetch in journal-chat-persist test: ${u}`)
    })
    vi.stubGlobal("fetch", fetchMock)
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.sessionStorage.clear()
  })

  it("shows the completed answer after unmount/remount, without duplicating the turn", async () => {
    // Initial load of entries list on mount
    on("/api/journal", () => jsonResponse({ entries: [] }))
    // Start the brainstorm
    on("/api/journal/chat", () => jsonResponse({ job_id: "job-1" }, 202))
    // Stream results (held until we release it)
    let releaseStream: (() => void) | null = null
    const gate = new Promise<void>((resolve) => { releaseStream = resolve })
    on("/api/chat/job-1/stream", async () => {
      await gate
      return sseStream([{ data: "final answer" }])
    })
    // Save the completed turn (POST to create new entry)
    on("/api/journal", () => jsonResponse({ id: "new-entry" }))
    // Load entries - should now include the newly created entry
    on("/api/journal", () =>
      jsonResponse({
        entries: [
          {
            id: "new-entry",
            date: "2024-01-15",
            size: 100,
            item: "what should I do",
            notion_url: ""
          }
        ]
      })
    )

    const { rerender } = render(<Shell showJournal={true} />)
    fireEvent.click(screen.getByRole("button", { name: /new/i }))
    const textarea = screen.getByPlaceholderText(/what should i focus on/i)
    fireEvent.change(textarea, { target: { value: "what should I do" } })
    fireEvent.click(screen.getByRole("button", { name: "Brainstorm" }))

    expect(await screen.findByTestId("journal-chat-thinking")).toHaveAccessibleName("Thinking…")

    // Navigate away: unmount JournalScreen but keep the providers/bridge
    // mounted, exactly like moving to another route under (main)/layout.tsx.
    rerender(<Shell showJournal={false} />)

    // Let the stream resolve while JournalScreen is unmounted.
    releaseStream!()

    // Wait for the bridge to complete the full cycle: stream ends → status=done →
    // Bridge POST → Bridge addTurn + setEntryId → sessionStorage persisted.
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/journal",
        expect.objectContaining({ method: "POST" }),
      )
    )

    // Navigate back.
    rerender(<Shell showJournal={true} />)

    // The panel should auto-open once the stores hydrate and the effect fires.
    // The question and answer should now appear in the brainstorm section
    // thanks to the persisted turns in sessionStorage. The question also
    // shows up a second time in the sidebar list, since it was refreshed
    // after the entry was saved.
    await waitFor(
      () => {
        expect(screen.getAllByText("what should I do").length).toBeGreaterThanOrEqual(2)
        expect(screen.getByText("final answer")).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
    expect(screen.queryByTestId("journal-chat-thinking")).toBeNull()
    // Exactly one save call, not one per remount.
    const saveCalls = fetchMock.mock.calls.filter(
      ([u, init]) => String(u) === "/api/journal" && (init as RequestInit | undefined)?.method === "POST",
    )
    expect(saveCalls).toHaveLength(1)
  })
})
