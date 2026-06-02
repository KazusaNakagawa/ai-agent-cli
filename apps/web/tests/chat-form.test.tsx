import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChatForm } from "@/components/screens/ChatForm"
import { ChatStateProvider } from "@/lib/chatStore"

function renderChatForm() {
  return render(
    <ChatStateProvider>
      <ChatForm />
    </ChatStateProvider>,
  )
}

type SSEPart = { event?: string; data: string }

// Build a Response whose body is a ReadableStream of well-formed SSE bytes.
function sseResponse(parts: SSEPart[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const p of parts) {
        let chunk = ""
        if (p.event) chunk += `event: ${p.event}\n`
        for (const line of p.data.split("\n")) chunk += `data: ${line}\n`
        chunk += "\n"
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
  return new Response(stream, { status: 200 })
}

describe("ChatForm", () => {
  const fetchMock = vi.fn()
  const DRAFT_KEY = "ai-agent:chat-draft:v1"

  // Per-URL response queue. URL-keyed (rather than vitest's global
  // once-queue) keeps the mount-time /api/credentials fetch from
  // accidentally consuming a chat-POST response.
  type Handler = (init?: RequestInit) => Promise<Response> | Response
  let queues: Record<string, Handler[]>

  function on(url: string, handler: Handler) {
    if (!queues[url]) queues[url] = []
    queues[url].push(handler)
  }

  function mockCreds(creds: Record<string, boolean> = {}) {
    return new Response(JSON.stringify(creds), {
      status: 200,
      headers: { "content-type": "application/json" },
    })
  }

  beforeEach(() => {
    queues = {}
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (url: string | URL, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      const queue = queues[u]
      if (queue && queue.length > 0) {
        const next = queue.shift()!
        return await next(init)
      }
      // Default credentials response so existing tests don't have to queue
      // one explicitly. Tests can override by calling on("/api/credentials", ...).
      if (u === "/api/credentials") return mockCreds()
      throw new Error(`Unmocked fetch in ChatForm test: ${u}`)
    })
    vi.stubGlobal("fetch", fetchMock)
    window.sessionStorage.clear()
    // Default: no SpeechRecognition (mimics Firefox / unsupported browsers).
    delete (window as unknown as { SpeechRecognition?: unknown })
      .SpeechRecognition
    delete (window as unknown as { webkitSpeechRecognition?: unknown })
      .webkitSpeechRecognition
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders the empty state and a disabled send button", () => {
    renderChatForm()
    expect(screen.getByTestId("chat-input")).toBeInTheDocument()
    expect(screen.getByTestId("send-button")).toBeDisabled()
  })

  it("enables send once the input is non-empty", async () => {
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "hi")
    expect(screen.getByTestId("send-button")).not.toBeDisabled()
  })

  it("POSTs today's date + question and streams assistant output", async () => {
    on("/api/chat", () => sseResponse([{ data: "hello" }, { data: "world" }]))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "what's new?")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      const assistant = screen.getByTestId("chat-msg-assistant")
      expect(assistant).toHaveTextContent("hello")
      expect(assistant).toHaveTextContent("world")
    })
    expect(screen.getByTestId("chat-msg-user")).toHaveTextContent("what's new?")

    const chatCall = fetchMock.mock.calls.find(
      ([u]) => u === "/api/chat",
    ) as [string, RequestInit] | undefined
    expect(chatCall).toBeDefined()
    expect(chatCall![1].method).toBe("POST")
    const body = JSON.parse(chatCall![1].body as string) as {
      date: string
      question: string
    }
    expect(body.question).toBe("what's new?")
    expect(body.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it("renders markdown in assistant output via react-markdown", async () => {
    on("/api/chat", () => sseResponse([{ data: "**bold** text" }]))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      const assistant = screen.getByTestId("chat-msg-assistant")
      expect(assistant.querySelector("strong")).toHaveTextContent("bold")
    })
  })

  it("retries exactly once on stale_session with the same payload", async () => {
    on("/api/chat", () =>
      sseResponse([{ event: "stale_session", data: "expired" }]),
    )
    on("/api/chat", () => sseResponse([{ data: "after retry" }]))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "after retry",
      )
    })
    const chatCalls = fetchMock.mock.calls.filter(
      ([u]) => u === "/api/chat",
    ) as Array<[string, RequestInit]>
    expect(chatCalls).toHaveLength(2)
    expect(chatCalls[0][1].body).toBe(chatCalls[1][1].body)
  })

  it("shows event:error inline and does not retry", async () => {
    on("/api/chat", () => sseResponse([{ event: "error", data: "boom" }]))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-error")).toHaveTextContent("boom")
    })
    const chatCalls = fetchMock.mock.calls.filter(([u]) => u === "/api/chat")
    expect(chatCalls).toHaveLength(1)
  })

  it("hides the mic button when SpeechRecognition is unavailable", () => {
    renderChatForm()
    expect(screen.queryByTestId("mic-button")).toBeNull()
    expect(screen.getByTestId("mic-unsupported")).toBeInTheDocument()
  })

  it("shows the mic button when SpeechRecognition is available", () => {
    class FakeRecognition {
      lang = ""
      continuous = false
      interimResults = false
      onresult: ((e: unknown) => void) | null = null
      onend: (() => void) | null = null
      onerror: ((e: unknown) => void) | null = null
      start() {}
      stop() {}
    }
    ;(window as unknown as { SpeechRecognition: unknown }).SpeechRecognition =
      FakeRecognition
    renderChatForm()
    expect(screen.getByTestId("mic-button")).toBeInTheDocument()
    expect(screen.queryByTestId("mic-unsupported")).toBeNull()
  })

  it("hydrates the input from sessionStorage on mount", async () => {
    window.sessionStorage.setItem(DRAFT_KEY, "draft in progress")
    renderChatForm()
    const input = await screen.findByTestId("chat-input")
    await waitFor(() => {
      expect(input).toHaveValue("draft in progress")
    })
  })

  it("persists the draft on each change and clears it on successful send", async () => {
    on("/api/chat", () => sseResponse([{ data: "ok" }]))
    const user = userEvent.setup()
    renderChatForm()
    const input = screen.getByTestId("chat-input")
    await user.type(input, "ab")
    await waitFor(() => {
      expect(window.sessionStorage.getItem(DRAFT_KEY)).toBe("ab")
    })
    await user.click(screen.getByTestId("send-button"))
    await waitFor(() => {
      expect(window.sessionStorage.getItem(DRAFT_KEY)).toBeNull()
    })
    expect(input).toHaveValue("")
  })

  it("shows the session-expired card on 401", async () => {
    on("/api/chat", () => new Response("", { status: 401 }))
    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    await waitFor(() => {
      expect(screen.getByTestId("session-expired")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("chat-input")).toBeNull()
  })

  // ----- Notion save (Issue #87) ----------------------------------------

  async function sendOneTurn(user: ReturnType<typeof userEvent.setup>) {
    on("/api/chat", () => sseResponse([{ data: "an answer" }]))
    await user.type(screen.getByTestId("chat-input"), "a question")
    await user.click(screen.getByTestId("send-button"))
    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "an answer",
      )
    })
  }

  it("disables the Notion button when credentials are absent", async () => {
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    const button = await screen.findByTestId("notion-save-button")
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute(
      "title",
      expect.stringContaining("Notion 認証情報が未設定"),
    )
  })

  it("disables the Notion button when only NOTION_API_KEY is set", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: false }),
    )
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    const button = await screen.findByTestId("notion-save-button")
    expect(button).toBeDisabled()
  })

  it("enables the Notion button when both NOTION_* keys are set", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: true }),
    )
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    await waitFor(() => {
      expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
    })
  })

  it("POSTs the Q&A on click and surfaces the returned URL", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: true }),
    )
    let importBody: string | null = null
    on("/api/chat/notion-import", (init) => {
      importBody = (init?.body as string) ?? null
      return new Response(
        JSON.stringify({ url: "https://www.notion.so/abc", summary: "ok" }),
        { status: 200, headers: { "content-type": "application/json" } },
      )
    })
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    await waitFor(() => {
      expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
    })
    // The model selector was removed (PR #110 review feedback): saving the
    // already-streamed answer doesn't benefit from a fresh model choice —
    // the only work left is a Notion API append, for which the backend
    // default (sonnet) is sufficient. So no UI control to assert here.
    expect(screen.queryByTestId("notion-model-select")).toBeNull()
    await user.click(screen.getByTestId("notion-save-button"))

    await waitFor(() => {
      expect(screen.getByTestId("notion-save-link")).toHaveAttribute(
        "href",
        "https://www.notion.so/abc",
      )
    })
    expect(screen.getByTestId("notion-save-button")).toBeDisabled()
    expect(importBody).not.toBeNull()
    const sent = JSON.parse(importBody!) as {
      date: string
      question: string
      answer: string
      model?: string
    }
    expect(sent.question).toBe("a question")
    expect(sent.answer).toBe("an answer")
    expect(sent.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    // model is omitted from the request body now that the UI no longer
    // surfaces a picker; the backend's Pydantic default (sonnet) kicks in.
    expect(sent.model).toBeUndefined()
  })

  it("keeps Notion save disabled while the assistant message is still streaming", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: true }),
    )

    // Hand-rolled SSE stream we can hold open: enqueue a partial chunk, let
    // the UI render, then assert the button is disabled before closing.
    const encoder = new TextEncoder()
    let controllerRef: ReadableStreamDefaultController<Uint8Array> | null = null
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controllerRef = controller
        controller.enqueue(encoder.encode("data: partial\n\n"))
      },
    })
    on("/api/chat", () => new Response(stream, { status: 200 }))

    const user = userEvent.setup()
    renderChatForm()
    await user.type(screen.getByTestId("chat-input"), "q")
    await user.click(screen.getByTestId("send-button"))

    // First chunk arrived — content rendered, button visible but disabled.
    await waitFor(() => {
      expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent(
        "partial",
      )
    })
    const button = screen.getByTestId("notion-save-button")
    expect(button).toBeDisabled()

    // Close the stream → busy flips false → button re-enables.
    controllerRef!.close()
    await waitFor(() => {
      expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
    })
  })

  it("surfaces the backend detail verbatim on 4xx (skill failure)", async () => {
    on("/api/credentials", () =>
      mockCreds({ NOTION_API_KEY: true, NOTION_DATABASE_ID: true }),
    )
    on("/api/chat/notion-import", () =>
      new Response(
        JSON.stringify({
          detail:
            "No Notion briefing page found for 2026-05-30 (skill report: 対象ページが見つかりませんでした)",
        }),
        { status: 404, headers: { "content-type": "application/json" } },
      ),
    )
    const user = userEvent.setup()
    renderChatForm()
    await sendOneTurn(user)
    await waitFor(() => {
      expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
    })
    await user.click(screen.getByTestId("notion-save-button"))

    await waitFor(() => {
      expect(screen.getByTestId("notion-save-error")).toHaveTextContent(
        "No Notion briefing page found for 2026-05-30",
      )
    })
    // After an error the button re-enables so the user can retry.
    expect(screen.getByTestId("notion-save-button")).not.toBeDisabled()
  })
})
