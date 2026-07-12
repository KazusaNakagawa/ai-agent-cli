import { fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { JournalScreen } from "@/components/screens/JournalScreen"
import { JournalSidebarList } from "@/components/journal/JournalSidebarList"
import { JournalChatJobStateProvider } from "@/lib/journalChatJobStore"
import { JournalChatStateProvider } from "@/lib/journalChatStore"
import { JournalNavProvider } from "@/lib/journalNavStore"

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

function renderJournalScreen() {
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

describe("JournalScreen voice input", () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    window.sessionStorage.clear()
    vi.stubGlobal("fetch", fetchMock)
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === "/api/journal" && (!init || !init.method || init.method === "GET")) {
        return Promise.resolve(jsonResponse({ entries: [] }))
      }
      return Promise.resolve(jsonResponse({}, 404))
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    window.sessionStorage.clear()
  })

  it("shows the fallback message when SpeechRecognition is unsupported", () => {
    renderJournalScreen()
    fireEvent.click(screen.getByRole("button", { name: /new/i }))

    expect(screen.queryByTestId("mic-button")).toBeNull()
    expect(screen.getByTestId("mic-unsupported")).toBeInTheDocument()
  })

  it("inserts recognized speech into the brainstorm textarea", () => {
    class FakeRecognition {
      lang = ""
      continuous = false
      interimResults = false
      onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null = null
      onend: (() => void) | null = null
      onerror: ((e: { error: string }) => void) | null = null
      start() {
        this.onresult?.({ results: [[{ transcript: "hello from voice" }]] })
      }
      stop() {
        this.onend?.()
      }
    }
    vi.stubGlobal("SpeechRecognition", FakeRecognition)

    renderJournalScreen()
    fireEvent.click(screen.getByRole("button", { name: /new/i }))

    const micButton = screen.getByTestId("mic-button")

    // Initial state: not listening.
    expect(micButton).toHaveAttribute("aria-pressed", "false")
    expect(micButton).toHaveAttribute("aria-label", "音声入力開始")
    expect(within(micButton).getByText("🎤")).toBeInTheDocument()

    fireEvent.click(micButton)

    // FakeRecognition.start() emits synchronously, so the transcript lands
    // before we assert the toggled-on state below.
    expect(micButton).toHaveAttribute("aria-pressed", "true")
    expect(micButton).toHaveAttribute("aria-label", "音声入力停止")
    expect(within(micButton).getByText("🛑")).toBeInTheDocument()

    const textarea = screen.getByPlaceholderText(
      /what should i focus on/i,
    ) as HTMLTextAreaElement
    expect(textarea.value).toBe("hello from voice")

    // Toggle off again and confirm the state resets.
    fireEvent.click(micButton)

    expect(micButton).toHaveAttribute("aria-pressed", "false")
    expect(micButton).toHaveAttribute("aria-label", "音声入力開始")
    expect(within(micButton).getByText("🎤")).toBeInTheDocument()
  })
})
