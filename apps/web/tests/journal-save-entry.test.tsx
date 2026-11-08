import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { JournalSidebarList } from "@/components/journal/JournalSidebarList"
import { JournalScreen } from "@/components/screens/JournalScreen"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"
import { JournalNavProvider } from "@/lib/journalNavStore"

vi.mock("next/navigation", () => ({ usePathname: () => "/journal" }))

type Entry = { id: string; date: string; size: number; item: string; notion_url: string }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

function renderJournal() {
  return render(
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

const EXISTING: Entry = {
  id: "2026-11-06_213000",
  date: "2026-11-06",
  size: 120,
  item: "Weekend reading",
  notion_url: "",
}

describe("JournalScreen — saving an entry without brainstorming", () => {
  const fetchMock = vi.fn()
  let entries: Entry[]
  let bodies: Record<string, string>

  beforeEach(() => {
    window.sessionStorage.clear()
    entries = []
    bodies = {}
    vi.stubGlobal("fetch", fetchMock)
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? "GET"
      if (url === "/api/journal" && method === "GET") {
        return Promise.resolve(jsonResponse({ entries }))
      }
      if (url === "/api/journal" && method === "POST") {
        const { content } = JSON.parse(String(init?.body)) as { content: string }
        const created: Entry = {
          id: "2026-11-08_090000",
          date: "2026-11-08",
          size: content.length,
          item: content.slice(0, 20),
          notion_url: "",
        }
        entries = [created, ...entries]
        bodies[created.id] = `# Journal 2026-11-08\n\n## 09:00:00\n\n${content}\n`
        return Promise.resolve(jsonResponse({ id: created.id, date: created.date }))
      }
      const patch = url.match(/^\/api\/journal\/([\w-]+)$/)
      if (patch && method === "PATCH") {
        const { content } = JSON.parse(String(init?.body)) as { content: string }
        bodies[patch[1]] = `${bodies[patch[1]] ?? ""}\n\n---\n\n${content}\n`
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      if (patch && method === "GET") {
        return Promise.resolve(jsonResponse({ id: patch[1], date: "2026-11-06", content: bodies[patch[1]] ?? "" }))
      }
      return Promise.resolve(jsonResponse({}, 404))
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    window.sessionStorage.clear()
  })

  function calls(method: string, url: string | RegExp) {
    return fetchMock.mock.calls.filter(([u, init]) => {
      const m = (init as RequestInit | undefined)?.method ?? "GET"
      return m === method && (typeof url === "string" ? String(u) === url : url.test(String(u)))
    })
  }

  it("saves the first entry from an empty journal and opens it", async () => {
    renderJournal()
    await waitFor(() => expect(calls("GET", "/api/journal")).toHaveLength(1))
    fireEvent.click(screen.getByRole("button", { name: /new/i }))
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "  First note today  " } })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => expect(calls("POST", "/api/journal")).toHaveLength(1))
    expect(JSON.parse(String(calls("POST", "/api/journal")[0][1]?.body))).toEqual({ content: "First note today" })
    // The new entry is listed and opened, and the composer is cleared.
    await waitFor(() => expect(screen.getByTestId("journal-panel-title")).toHaveTextContent("First note today"))
    expect(await screen.findByText("First note today", { selector: "[data-testid='journal-content'] *" })).toBeInTheDocument()
    expect((screen.getByTestId("chat-input") as HTMLTextAreaElement).value).toBe("")
    // Saving never starts a brainstorm.
    expect(calls("POST", "/api/journal/chat")).toHaveLength(0)
  })

  it("appends to the open entry", async () => {
    entries = [EXISTING]
    bodies[EXISTING.id] = "# Journal 2026-11-06\n\n## 21:30:00\n\nOriginal text\n"
    renderJournal()
    fireEvent.click(await screen.findByText("Weekend reading"))
    await screen.findByText("Original text")
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Follow-up thought" } })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => expect(calls("PATCH", `/api/journal/${EXISTING.id}`)).toHaveLength(1))
    expect(JSON.parse(String(calls("PATCH", `/api/journal/${EXISTING.id}`)[0][1]?.body))).toEqual({ content: "Follow-up thought" })
    expect(await screen.findByText("Follow-up thought")).toBeInTheDocument()
    expect(calls("POST", "/api/journal")).toHaveLength(0)
  })

  it("keeps the text and shows an error when saving fails", async () => {
    renderJournal()
    await waitFor(() => expect(calls("GET", "/api/journal")).toHaveLength(1))
    const base = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) =>
      String(input) === "/api/journal" && init?.method === "POST"
        ? Promise.resolve(new Response("boom", { status: 500 }))
        : base(input, init),
    )
    fireEvent.click(screen.getByRole("button", { name: /new/i }))
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Will this save?" } })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    expect(await screen.findByText(/Save failed \(HTTP 500\)/)).toBeInTheDocument()
    expect((screen.getByTestId("chat-input") as HTMLTextAreaElement).value).toBe("Will this save?")
  })

  it("disables Save for empty or whitespace-only text", async () => {
    renderJournal()
    await waitFor(() => expect(calls("GET", "/api/journal")).toHaveLength(1))
    fireEvent.click(screen.getByRole("button", { name: /new/i }))
    const save = screen.getByRole("button", { name: "Save" })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "   \n " } })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "x" } })
    expect(save).toBeEnabled()
  })

  it("steers an empty journal to Save instead of a brainstorm that cannot run", async () => {
    renderJournal()
    await waitFor(() => expect(calls("GET", "/api/journal")).toHaveLength(1))
    fireEvent.click(screen.getByRole("button", { name: /new/i }))
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "hello" } })
    expect(await screen.findByTestId("journal-empty-hint")).toHaveTextContent(/save/i)
    expect(screen.getByRole("button", { name: "Brainstorm" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled()
  })

  it("does not treat the journal as empty before the list has loaded", async () => {
    let release: (r: Response) => void = () => {}
    const base = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) =>
      String(input) === "/api/journal" && (init?.method ?? "GET") === "GET"
        ? new Promise<Response>((resolve) => { release = resolve })
        : base(input, init),
    )
    renderJournal()
    fireEvent.click(screen.getByRole("button", { name: /new/i }))
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "hello" } })
    expect(screen.queryByTestId("journal-empty-hint")).toBeNull()
    expect(screen.getByRole("button", { name: "Brainstorm" })).toBeEnabled()
    release(jsonResponse({ entries: [] }))
    expect(await screen.findByTestId("journal-empty-hint")).toBeInTheDocument()
  })

  it("allows brainstorming once the journal has an entry", async () => {
    entries = [EXISTING]
    renderJournal()
    await screen.findByText("Weekend reading")
    fireEvent.click(screen.getByRole("button", { name: /new/i }))
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "hello" } })
    expect(screen.getByRole("button", { name: "Brainstorm" })).toBeEnabled()
    expect(screen.queryByTestId("journal-empty-hint")).toBeNull()
  })
})
